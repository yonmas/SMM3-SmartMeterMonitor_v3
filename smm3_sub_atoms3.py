"""
SMM3 ATOM - 4モード切り替え
CircuitPython on ATOM S3 (128×128)

ボタン短押しでモード切り替え:
  MODE_SIMPLE : 瞬時電力を右寄せ大型表示＋累積電力量・料金
  MODE_TODAY  : 今日の30分刻みグラフ（6時間グループ）
  MODE_WEEK   : 週間横棒グラフ（Today+7日、2トーン・日付付き）
  MODE_MONTH  : 30日横棒グラフ（モニタリング用）
"""

import os
import time
import struct
import array
import wifi
import espnow
import board
import busio
import digitalio
import displayio
import terminalio
from adafruit_display_text import label
from adafruit_bitmap_font import bitmap_font

# ---- モード ----
MODE_SIMPLE = 0
MODE_TODAY  = 1
MODE_WEEK   = 2
MODE_MONTH  = 3

# ---- カラー ----
BG_COLOR      = 0x102030
COLOR_LOW     = 0x00DD88
COLOR_MID     = 0x1F77B4   # M5Stack版 color1（通常時）に合わせた
COLOR_HIGH    = 0xFF8800
COLOR_WARN    = 0xD62728   # M5Stack版 color3（警告時）に合わせた
COLOR_UNIT    = 0x445566
COLOR_TOTAL   = 0xE08040   # M5Stack版 color2（今月累積電力量・料金）
COLOR_UNCOLOR = 0xA0A0A0   # M5Stack版 uncolor（単位文字）
COLOR_BAR          = 0x0088CC   # 今日グラフ（30分棒）
# 週グラフ（M5Stack版に合わせた配色）
COLOR_WEEK_TODAY_E = 0x2CD02C   # 今日バー縁 / 縦線（明緑）
COLOR_WEEK_TODAY_F = 0x2C802C   # 今日バー塗り（暗緑）
COLOR_WEEK_WARN_E  = 0xD02020   # 今日バー縁・警告（明赤）
COLOR_WEEK_WARN_F  = 0x802020   # 今日バー塗り・警告（暗赤）
COLOR_WEEK_EDGE    = 0x0095AD   # 過去バー縁（シアン）
COLOR_WEEK_CUMUL   = 0x104040   # 過去バー・終日塗り（暗ティール）
COLOR_WEEK_PART    = 0x19758D   # 過去バー・現時点塗り（スチールブルー）
COLOR_WEEK_AVG     = 0x0000A0   # 平均バー・現時点塗り（青）
# 旧エイリアス（MODE_SIMPLE/TODAY 向け、互換用）
COLOR_TODAY_W = COLOR_WEEK_TODAY_E

WARNING_AMPERAGE = 30
UNIT = 0.1   # kWh / raw unit（日本のスマートメーター標準）

# ---- watt表示 共通定数（MODE_SIMPLE/MODE_TODAY共通） ----
WATT_BOTTOM_Y = 42    # 瞬時電力値の下端y
WATT_RIGHT_X  = 109   # 瞬時電力値の右端x（"W"と重ならない位置）

# ---- 今日グラフ定数 ----
TODAY_GRAPH_GAP = 4   # 数値ブロックとグラフの隙間(px)
TODAY_BORDER_H  = 1   # 上下端横線の高さ(px、それぞれ)
TODAY_LABEL_H   = 10  # 下端横線の下の時刻インデックス分の余白(px)
GRAPH_Y = WATT_BOTTOM_Y + TODAY_GRAPH_GAP
GRAPH_H = 128 - GRAPH_Y - TODAY_LABEL_H - 2 * TODAY_BORDER_H - 1   # 余った分をグラフに割り当て（下端を1px上げる）
DAY_GRAPH_SCALE = 1.0   # kWh/30min, 縦軸フルスケール
DAY_TH_WARNING  = 0.6   # kWh/30min, 警告域（橙）
DAY_TH_ADVISORY = 0.3   # kWh/30min, 予告域（黄）

TODAY_SLOT_W  = 2    # 1スロット(30分)の幅(px)
TODAY_GROUP_N = 12   # 1グループ(6時間)のスロット数
TODAY_GROUPS  = 4
TODAY_GAP     = 3    # グループ間の隙間(px)
_today_total_w = TODAY_SLOT_W * TODAY_GROUP_N * TODAY_GROUPS + TODAY_GAP * (TODAY_GROUPS - 1)
_today_start_x = (128 - _today_total_w) // 2

_TODAY_XS = []
_TODAY_VLINES = [_today_start_x - 2]   # 両端（バーと1px空ける）＋グループ間の隙間中央
_x = _today_start_x
for _g in range(TODAY_GROUPS):
    for _ in range(TODAY_GROUP_N):
        _TODAY_XS.append(_x)
        _x += TODAY_SLOT_W
    if _g < TODAY_GROUPS - 1:
        _TODAY_VLINES.append(_x + TODAY_GAP // 2)
        _x += TODAY_GAP
_TODAY_VLINES.append(_x + 1)

# ---- 週グラフ定数 ----
BAR_X    = 14    # バー左端X
MAX_BAR  = 94    # バー最大幅(px)
GRAPH_FILL_RATIO = 0.9  # 最大値がバー最大幅に対して占める割合（残りは余白）
BAR_H    = 10    # バー高さ(px)
ROW_STEP = 13    # 行ピッチ（バー10px + 隙間3px）
# 今日の後・AVG前に1px追加、全体を上下中央寄せ（上下マージン各6px）
ROW_Y = [6, 20, 33, 46, 59, 72, 85, 98]  # ROW_Y[0→1]=14(+1), 以降13px
AVG_Y = 112  # = ROW_Y[7]+14（AVG前にも1px追加）

# ---- 月グラフ定数 ----
# バー: 1px境界+2px中+1px境界=4px、境界共有で3px/スロット、7本=22px
# 30日=4グループ(28日)+2日、余り27px: 当日エリア14px/avgエリア13px（中央揃え）
# 当日8px(上下マージン各3px) / avg8px(上マージン2px、下マージン3px)
MONTH_TODAY_Y = 3   # 当日バー開始y（上マージン3px）
MONTH_TODAY_H = 8   # 当日バー高さ（縁1+中6+縁1）
MONTH_ROW_Y = (
    [0]                                             # 今日: y=0..13
    + [15 + (i - 1)  * 3 for i in range(1, 8)]     # グループ1: rows 1-7,   y=15..33
    + [38 + (i - 8)  * 3 for i in range(8, 15)]    # グループ2: rows 8-14,  y=38..56
    + [61 + (i - 15) * 3 for i in range(15, 22)]   # グループ3: rows 15-21, y=61..79
    + [84 + (i - 22) * 3 for i in range(22, 29)]   # グループ4: rows 22-28, y=84..102
    + [107 + (i - 29) * 3 for i in range(29, 31)]  # グループ5: rows 29-30, y=107..110
)
MONTH_AVG_Y = 117  # avg: y=117..124（縁1+中6+縁1=8px、上マージン2px）
MONTH_SEP_Y = [14, 37, 60, 83, 106, 114]  # sep位置（当日後/グループ間/avg前）


def watt_color(w, a):
    if a >= WARNING_AMPERAGE:
        return COLOR_WARN
    else:
        return COLOR_MID
    # if w < 500:
    #     return COLOR_LOW
    # if w < 2000:
    #     return COLOR_MID
    # if w < 3000:
    #     return COLOR_HIGH
    # return COLOR_WARN

# ---- IMU (MPU6886) ----
_MPU_ADDR   = 0x68
_PWR_MGMT_1 = 0x6B
_ACCEL_XOUT = 0x3B

try:
    _i2c = busio.I2C(scl=board.IMU_SCL, sda=board.IMU_SDA)
except AttributeError:
    _i2c = board.I2C()

while not _i2c.try_lock():
    pass
_i2c.writeto(_MPU_ADDR, bytes([_PWR_MGMT_1, 0x00]))
_i2c.unlock()


def read_accel():
    while not _i2c.try_lock():
        pass
    _i2c.writeto(_MPU_ADDR, bytes([_ACCEL_XOUT]))
    buf = bytearray(6)
    _i2c.readfrom_into(_MPU_ADDR, buf)
    _i2c.unlock()
    ax, ay, az = struct.unpack(">hhh", buf)
    return ax / 16384.0, ay / 16384.0, az / 16384.0


def accel_to_rotation(ax, ay):
    if abs(ax) > abs(ay):
        return 270 if ax > 0 else 90
    return 0 if ay < 0 else 180


# ---- ボタン ----
_btn = digitalio.DigitalInOut(board.BTN)
_btn.direction = digitalio.Direction.INPUT
_btn.pull = digitalio.Pull.UP
BTN_LONGPRESS_T = 0.6   # 長押し判定(秒)

# ---- ディスプレイ ----
display    = board.DISPLAY
BRIGHTNESS_LEVELS = (0.5, 0.7, 0.9)   # 長押しでこの順に循環
display.brightness = BRIGHTNESS_LEVELS[0]
font_dseg7_main = bitmap_font.load_font("/fonts/DSEG7Classic-Bold-32.bdf")
font_cuml       = bitmap_font.load_font("/fonts/Arial-Bold-18.bdf")
font_arial_b12  = bitmap_font.load_font("/fonts/Arial-Bold-12.bdf")


def _make_bg():
    b = displayio.Bitmap(128, 128, 1)
    p = displayio.Palette(1)
    p[0] = BG_COLOR
    return displayio.TileGrid(b, pixel_shader=p)


# ========== グループ0: シンプル（右寄せ大型＋累積電力量・料金） ==========
PERIOD_Y         = 68    # 電気料金計算期間表示の下端y
CUML_VALUE_Y     = 97    # 累積電力量・料金（数値）の下端y（単位ごと2px下げ）
CUML_UNIT_Y      = 117   # 累積電力量・料金（単位）の下端y（単位ごと2px下げ）
CUML_ONE_CHAR_W  = 6     # 単位を数値右端から右にはみ出させる量（1文字分）
CUML_KWH_RIGHT_X = 46    # 累積電力量（数値）の右端x（3桁時の左マージンが4pxになる位置）
CUML_YEN_RIGHT_X = 121   # 料金（数値）の右端x（画面端126から3px左）

g0 = displayio.Group()
g0.append(_make_bg())

g0_watt = label.Label(font_dseg7_main, text="---", color=COLOR_MID)
g0_watt.anchor_point = (1.0, 1.0)
g0_watt.anchored_position = (WATT_RIGHT_X, WATT_BOTTOM_Y)
g0.append(g0_watt)

g0_w = label.Label(font_arial_b12, text="W", color=COLOR_UNCOLOR)
g0_w.anchor_point = (1.0, 1.0)
g0_w.anchored_position = (126, WATT_BOTTOM_Y)
g0.append(g0_w)

# 電気料金計算期間（検針日起点の日付範囲、M5Stack版draw_main参考）
g0_period = label.Label(font_arial_b12, text="", color=COLOR_UNCOLOR)
g0_period.anchor_point = (0.5, 1.0)
g0_period.anchored_position = (64, PERIOD_Y)
g0.append(g0_period)

# 今月（検針日起点）の累積電力量・料金（M5Stack版draw_main参考のプロトタイプ）
g0_cuml_kwh_val = label.Label(font_cuml, text="", color=COLOR_TOTAL)
g0_cuml_kwh_val.anchor_point = (1.0, 1.0)
g0_cuml_kwh_val.anchored_position = (CUML_KWH_RIGHT_X, CUML_VALUE_Y)
g0.append(g0_cuml_kwh_val)

g0_cuml_kwh_unit = label.Label(font_arial_b12, text="kWh", color=COLOR_UNCOLOR)
g0_cuml_kwh_unit.anchor_point = (1.0, 1.0)
g0_cuml_kwh_unit.anchored_position = (CUML_KWH_RIGHT_X + CUML_ONE_CHAR_W, CUML_UNIT_Y)
g0.append(g0_cuml_kwh_unit)

g0_cuml_yen_val = label.Label(font_cuml, text="", color=COLOR_TOTAL)
g0_cuml_yen_val.anchor_point = (1.0, 1.0)
g0_cuml_yen_val.anchored_position = (CUML_YEN_RIGHT_X, CUML_VALUE_Y)
g0.append(g0_cuml_yen_val)

g0_cuml_yen_unit = label.Label(font_arial_b12, text="Yen", color=COLOR_UNCOLOR)
g0_cuml_yen_unit.anchor_point = (1.0, 1.0)
g0_cuml_yen_unit.anchored_position = (CUML_YEN_RIGHT_X + CUML_ONE_CHAR_W, CUML_UNIT_Y)
g0.append(g0_cuml_yen_unit)

# ========== グループ1: 今日グラフ ==========
g1 = displayio.Group()
g1.append(_make_bg())

today_bmp = displayio.Bitmap(128, GRAPH_H + 2 * TODAY_BORDER_H, 8)
today_pal = displayio.Palette(8)
today_pal[0] = BG_COLOR
today_pal[1] = 0x404060   # 前日グレー
today_pal[2] = 0x19758D   # 今日通常（青）
today_pal[3] = 0xEED070   # 今日予告（黄）
today_pal[4] = 0xEE8040   # 今日警告（橙）
today_pal[5] = 0xF04040   # 前日超過（赤）
today_pal[6] = 0x303030   # グループ境界縦線（M5Stack版準拠）
today_pal[7] = 0xAEAEAE   # 上下端横線（M5Stack版準拠）
g1.append(displayio.TileGrid(today_bmp, pixel_shader=today_pal, x=0, y=GRAPH_Y))

g1_watt = label.Label(font_dseg7_main, text="---", color=COLOR_MID)
g1_watt.anchor_point = (1.0, 1.0)
g1_watt.anchored_position = (WATT_RIGHT_X, WATT_BOTTOM_Y)
g1.append(g1_watt)

g1_w = label.Label(font_arial_b12, text="W", color=COLOR_UNCOLOR)
g1_w.anchor_point = (1.0, 1.0)
g1_w.anchored_position = (126, WATT_BOTTOM_Y)
g1.append(g1_w)

for _vx, _hh in zip(_TODAY_VLINES, (0, 6, 12, 18, 24)):
    _tl = label.Label(terminalio.FONT, text=f"{_hh:02d}", color=0x778899)
    _tl.anchor_point = (0.5, 0.0)
    _tl.anchored_position = (_vx, GRAPH_Y + GRAPH_H + 2 * TODAY_BORDER_H)
    g1.append(_tl)

# ========== グループ2: 週グラフ ==========
g2 = displayio.Group()

# 7色ビットマップ（M5Stack版に合わせた縁取り配色）
# 0=BG, 1=今日縁/縦線, 2=今日塗り, 3=過去縁, 4=過去終日塗り, 5=過去現時点塗り, 6=平均現時点塗り
week_bmp = displayio.Bitmap(128, 128, 7)
week_pal = displayio.Palette(7)
week_pal[0] = BG_COLOR
week_pal[1] = COLOR_WEEK_TODAY_E
week_pal[2] = COLOR_WEEK_TODAY_F
week_pal[3] = COLOR_WEEK_EDGE
week_pal[4] = COLOR_WEEK_CUMUL
week_pal[5] = COLOR_WEEK_PART
week_pal[6] = COLOR_WEEK_AVG
g2.append(displayio.TileGrid(week_bmp, pixel_shader=week_pal))

# 日付ラベル（左列・右寄せ）と kWhラベル（右列）
g2_date = []
g2_kwh  = []
for _i in range(8):
    _y = ROW_Y[_i] + 5  # バー行の中央
    d_lbl = label.Label(terminalio.FONT, text="--", color=0x778899)
    d_lbl.anchor_point = (1.0, 0.5)
    d_lbl.anchored_position = (BAR_X - 1, _y)
    g2.append(d_lbl)
    g2_date.append(d_lbl)

    k_lbl = label.Label(terminalio.FONT, text="", color=0xAABBCC)
    k_lbl.anchor_point = (1.0, 0.5)
    k_lbl.anchored_position = (127, _y)
    g2.append(k_lbl)
    g2_kwh.append(k_lbl)

# 平均行ラベル（左: "AV" 右寄せ、右: kWh値）
_avg_mid = AVG_Y + 5
g2_avg_lbl = label.Label(terminalio.FONT, text="AV", color=0x778899)
g2_avg_lbl.anchor_point = (1.0, 0.5)
g2_avg_lbl.anchored_position = (BAR_X - 1, _avg_mid)
g2.append(g2_avg_lbl)

g2_avg_kwh = label.Label(terminalio.FONT, text="", color=0xAABBCC)
g2_avg_kwh.anchor_point = (1.0, 0.5)
g2_avg_kwh.anchored_position = (127, _avg_mid)
g2.append(g2_avg_kwh)

# 起動時は今日ラベルだけ設定
g2_date[0].text = "TD"

# ========== グループ3: 月グラフ ==========
g3 = displayio.Group()
month_bmp = displayio.Bitmap(128, 128, 8)
month_pal = displayio.Palette(8)
month_pal[0] = BG_COLOR
month_pal[1] = COLOR_WEEK_TODAY_E
month_pal[2] = COLOR_WEEK_TODAY_F
month_pal[3] = COLOR_WEEK_EDGE
month_pal[4] = COLOR_WEEK_CUMUL
month_pal[5] = COLOR_WEEK_PART
month_pal[6] = COLOR_WEEK_AVG
month_pal[7] = 0x303030  # 7日仕切り線
g3.append(displayio.TileGrid(month_bmp, pixel_shader=month_pal))

_g3_td_lbl = label.Label(terminalio.FONT, text="TD", color=0x778899)
_g3_td_lbl.anchor_point = (1.0, 0.5)
_g3_td_lbl.anchored_position = (BAR_X - 1, 7)  # 今日バー中央
g3.append(_g3_td_lbl)

g3_today_kwh = label.Label(terminalio.FONT, text="", color=0xAABBCC)
g3_today_kwh.anchor_point = (1.0, 0.5)
g3_today_kwh.anchored_position = (127, 7)   # 今日バー中央 y=0..13 → 7
g3.append(g3_today_kwh)

_g3_av_lbl = label.Label(terminalio.FONT, text="AV", color=0x778899)
_g3_av_lbl.anchor_point = (1.0, 0.5)
_g3_av_lbl.anchored_position = (BAR_X - 1, 121)  # avgバー中央
g3.append(_g3_av_lbl)

g3_avg_kwh = label.Label(terminalio.FONT, text="", color=0xAABBCC)
g3_avg_kwh.anchor_point = (1.0, 0.5)
g3_avg_kwh.anchored_position = (127, 121)  # avgバー中央 y=115..127 → 121
g3.append(g3_avg_kwh)

# グループ末 7日ごとセパレーター上の日付ラベル（日のみ、右寄せ）
g3_sep_dates = []
for _sy in [37, 60, 83, 106]:
    _dl = label.Label(terminalio.FONT, text="", color=0x778899)
    _dl.anchor_point = (1.0, 1.0)
    _dl.anchored_position = (BAR_X - 1, _sy)
    g3.append(_dl)
    g3_sep_dates.append(_dl)

# ---- 取得インジケーター（右下3x3px、全グループ共用パレット）----
ind_bmp = displayio.Bitmap(2, 2, 2)
ind_bmp.fill(1)
ind_pal = displayio.Palette(2)
ind_pal[0] = BG_COLOR
ind_pal[1] = BG_COLOR  # 初期は消灯
for _g in [g0, g1, g2, g3]:
    _g.append(displayio.TileGrid(ind_bmp, pixel_shader=ind_pal, x=126, y=126))

display.root_group = g0


# ---- 今日グラフ描画 ----
def draw_today():
    today_bmp.fill(0)
    for _x in range(128):
        today_bmp[_x, 0] = 7              # 上端横線
        today_bmp[_x, GRAPH_H + 1] = 7     # 下端横線
    for _vx in _TODAY_VLINES:
        for _y in range(1, GRAPH_H + 1):
            today_bmp[_vx, _y] = 6

    hist49 = hist_week[0]
    yest   = hist_week[1]
    if hist49 is None:
        return
    for n in range(48):
        if hist49[n] == 0 or hist49[n + 1] == 0:
            kwh_t = 0.0
        else:
            kwh_t = max(0.0, (hist49[n + 1] - hist49[n]) * UNIT)
        if yest is None or yest[n] == 0 or yest[n + 1] == 0:
            kwh_y = 0.0
        else:
            kwh_y = max(0.0, (yest[n + 1] - yest[n]) * UNIT)
        h_t = min(int(kwh_t * (GRAPH_H - 2) / DAY_GRAPH_SCALE), GRAPH_H - 2)
        h_y = min(int(kwh_y * (GRAPH_H - 2) / DAY_GRAPH_SCALE), GRAPH_H - 2)
        if kwh_t >= DAY_TH_WARNING:
            col_t = 4          # 橙
        elif kwh_t >= DAY_TH_ADVISORY:
            col_t = 3          # 黄
        else:
            col_t = 2          # 青
        x0 = _TODAY_XS[n]
        for row in range(max(h_t, h_y)):
            if row < h_t and row < h_y:
                px = col_t     # 今日・前日重複 → 今日色
            elif row < h_y:
                px = 1         # 前日のみ → グレー
            else:
                px = 5         # 今日が前日超過 → 赤
            y = GRAPH_H - row  # 上端横線(row0)分シフト
            today_bmp[x0,     y] = px
            today_bmp[x0 + 1, y] = px


# ---- 週グラフ描画 ----
def estimate_current_slot():
    """今日の累積値から現在の30分スロット番号(0-48)を推定"""
    if hist_week[0] is None:
        return 48
    base = hist_week[0][0]
    last = 0
    for i in range(1, 49):
        if hist_week[0][i] > base:
            last = i
    return last


def _bar(y0, w, edge_c, fill_c, bmp=None, h=None):
    """縁取りありの横棒を bmp に描画（省略時は week_bmp / BAR_H）"""
    if bmp is None: bmp = week_bmp
    if h is None: h = BAR_H
    if w <= 0:
        return
    for y in range(y0, y0 + h):
        for x in range(BAR_X, BAR_X + w):
            bmp[x, y] = edge_c
    if w > 2 and h > 2:
        for y in range(y0 + 1, y0 + h - 1):
            for x in range(BAR_X + 1, BAR_X + w - 1):
                bmp[x, y] = fill_c


def draw_week_bars():
    slot = estimate_current_slot()

    full_raw = []  # 表示用合計（今日=現時点まで, 過去=終日）
    part_raw = []  # 各日の現時点スロットまで合計
    for d in range(8):
        if hist_week[d] is not None:
            if d == 0:
                v = max(0, hist_week[0][min(slot, 48)] - hist_week[0][0])
                full_raw.append(v)
                part_raw.append(v)
            else:
                f = max(0, hist_week[d][48] - hist_week[d][0])
                p = max(0, hist_week[d][min(slot, 48)] - hist_week[d][0])
                full_raw.append(f)
                part_raw.append(p)
        else:
            full_raw.append(0)
            part_raw.append(0)

    max_v = (max(full_raw) / GRAPH_FILL_RATIO) if max(full_raw) > 0 else 1

    # 平均計算（今日との比較で今日バー色を決定）
    avg_full = 0; avg_part = 0; n = 0
    for d in range(1, 8):
        if hist_week[d] is not None and full_raw[d] > 0:
            avg_full += full_raw[d]; avg_part += part_raw[d]; n += 1
    if n > 0:
        avg_full /= n; avg_part /= n

    if n > 0 and avg_part > 0 and part_raw[0] > avg_part:
        week_pal[1] = COLOR_WEEK_WARN_E
        week_pal[2] = COLOR_WEEK_WARN_F
    else:
        week_pal[1] = COLOR_WEEK_TODAY_E
        week_pal[2] = COLOR_WEEK_TODAY_F

    week_bmp.fill(0)

    for i in range(8):
        y0 = ROW_Y[i]
        fw = int((full_raw[i] / max_v) * MAX_BAR)
        pw = int((part_raw[i] / max_v) * MAX_BAR)
        if i == 0:
            # 今日: fw==pw なので1段描画（縁pal[1] + 塗りpal[2]）
            _bar(y0, fw, 1, 2)
        else:
            # 過去: 終日バー（暗）→ 現時点バー（明）で上書き
            _bar(y0, fw, 3, 4)
            _bar(y0, pw, 3, 5)

    # 平均バー
    _bar(AVG_Y, int((avg_full / max_v) * MAX_BAR), 3, 4)
    _bar(AVG_Y, int((avg_part / max_v) * MAX_BAR), 3, 6)

    # 現在時刻縦線（明緑、今日バー右端と同列から画面下端）
    lx = BAR_X + int((part_raw[0] / max_v) * MAX_BAR) - 1
    lx = min(max(lx, BAR_X), BAR_X + MAX_BAR - 1)
    shadow_start = ROW_Y[0] + BAR_H  # 今日バーの下端から
    if lx > BAR_X:
        for y in range(shadow_start, 128):
            week_bmp[lx - 1, y] = 0  # 地の色で影
    for y in range(ROW_Y[0], 128):
        week_bmp[lx, y] = 1

    # ---- ラベル更新 ----
    for i in range(8):
        if hist_week[i] is not None:
            g2_kwh[i].text = f"{part_raw[i] * UNIT:.1f}"
        else:
            g2_kwh[i].text = ""

    g2_avg_kwh.text = f"{avg_part * UNIT:.1f}" if n > 0 else ""


# ---- 月グラフ描画 ----
def draw_month_bars():
    slot = estimate_current_slot()

    full_raw = []
    part_raw = []
    for d in range(31):  # 今日 + 30日分（rows 0-30）
        if hist_week[d] is not None:
            if d == 0:
                v = max(0, hist_week[0][min(slot, 48)] - hist_week[0][0])
                full_raw.append(v); part_raw.append(v)
            else:
                f = max(0, hist_week[d][48] - hist_week[d][0])
                p = max(0, hist_week[d][min(slot, 48)] - hist_week[d][0])
                full_raw.append(f); part_raw.append(p)
        else:
            full_raw.append(0); part_raw.append(0)

    max_v = (max(full_raw) / GRAPH_FILL_RATIO) if max(full_raw) > 0 else 1

    # 平均計算（今日との比較で今日バー色を決定）
    avg_full = 0; avg_part = 0; n = 0
    for d in range(1, 31):
        if hist_week[d] is not None and full_raw[d] > 0:
            avg_full += full_raw[d]; avg_part += part_raw[d]; n += 1
    if n > 0:
        avg_full /= n; avg_part /= n

    if n > 0 and avg_part > 0 and part_raw[0] > avg_part:
        month_pal[1] = COLOR_WEEK_WARN_E
        month_pal[2] = COLOR_WEEK_WARN_F
    else:
        month_pal[1] = COLOR_WEEK_TODAY_E
        month_pal[2] = COLOR_WEEK_TODAY_F

    month_bmp.fill(0)

    # 今日バー（標準縁取り、8px、上マージンMONTH_TODAY_Y=3px）
    fw0 = int((full_raw[0] / max_v) * MAX_BAR)
    _bar(MONTH_TODAY_Y, fw0, 1, 2, month_bmp, MONTH_TODAY_H)

    # 過去バー（境界共有、3px/slot）
    # 現時刻まで(pw): 上下端境界(3)+左右縦線(3)+中塗り(5)
    # 現時刻以降(fw-pw): 縁取りなし、塗り(4)のみ
    for i in range(1, 31):  # rows 1-30
        y0 = MONTH_ROW_Y[i]
        fw = int((full_raw[i] / max_v) * MAX_BAR)
        pw = int((part_raw[i] / max_v) * MAX_BAR)
        if fw == 0:
            continue
        # 上端行: 現時刻まで境界(3)、以降は塗り(4)
        for x in range(BAR_X, BAR_X + pw):
            month_bmp[x, y0] = 3
        for x in range(BAR_X + pw, BAR_X + fw):
            month_bmp[x, y0] = 4
        # 塗り2行
        for yr in (y0 + 1, y0 + 2):
            for x in range(BAR_X, BAR_X + fw):
                month_bmp[x, yr] = 4
            if pw > 0:
                month_bmp[BAR_X, yr] = 3              # 左縦線
                if pw > 1:
                    month_bmp[BAR_X + pw - 1, yr] = 3  # 右縦線
                for x in range(BAR_X + 1, BAR_X + pw - 1):
                    month_bmp[x, yr] = 5               # 中塗り
        # 下端行: 現時刻まで境界(3)、以降は塗り(4)（常に描画）
        for x in range(BAR_X, BAR_X + pw):
            month_bmp[x, y0 + 3] = 3
        for x in range(BAR_X + pw, BAR_X + fw):
            month_bmp[x, y0 + 3] = 4

    # 平均バー（標準縁取り、8px、avg_full/avg_partは先頭で計算済み）
    _bar(MONTH_AVG_Y, int((avg_full / max_v) * MAX_BAR), 3, 4, month_bmp, 8)
    _bar(MONTH_AVG_Y, int((avg_part / max_v) * MAX_BAR), 3, 6, month_bmp, 8)

    # セパレーター（グループ間・今日後・avg前）
    for _sy in MONTH_SEP_Y:
        for _x in range(128):
            month_bmp[_x, _sy] = 7

    # ラベル更新（当日・平均）
    if hist_week[0] is not None:
        g3_today_kwh.text = f"{part_raw[0] * UNIT:.1f}"
    g3_avg_kwh.text = f"{avg_part * UNIT:.1f}" if n > 0 else ""

    # 日付ラベル（グループ末尾日、セパレーター上）
    for _j, _dr in enumerate([7, 14, 21, 28]):
        _parts = hist_date[_dr].split("/")
        g3_sep_dates[_j].text = _parts[1] if len(_parts) == 2 and _parts[1] != "--" else ""

    # 現在時刻縦線
    lx = BAR_X + int((part_raw[0] / max_v) * MAX_BAR) - 1
    lx = min(max(lx, BAR_X), BAR_X + MAX_BAR - 1)
    if lx > BAR_X:
        for y in range(MONTH_TODAY_Y + MONTH_TODAY_H, 128):
            month_bmp[lx - 1, y] = 0
    for y in range(MONTH_TODAY_Y + MONTH_TODAY_H, 128):
        month_bmp[lx, y] = 1


# ---- WiFi & ESP-NOW ----
ssid     = os.getenv("WIFI_SSID")
password = os.getenv("WIFI_PASSWORD")

if ssid:
    try:
        wifi.radio.connect(ssid, password)
    except Exception:
        wifi.radio.enabled = True
else:
    wifi.radio.enabled = True

e     = espnow.ESPNow()
bcast = espnow.Peer(mac=b"\xff\xff\xff\xff\xff\xff", encrypted=False)
e.peers.append(bcast)


def send_req(day):
    try:
        e.send(f"REQ{day:02d}".encode(), bcast)
        print(f"[SEND] REQ{day:02d}")
    except Exception as ex:
        print(f"[SEND] REQ{day:02d} ERROR: {ex}")


# ---- 状態変数 ----
wattage    = 0
amperage   = 0.0
monthly_kwh = 0    # 今月（検針日起点）の累積電力量
charge_yen  = 0    # 今月（検針日起点）の電気料金
hist_week  = [None] * 31  # [0]=今日〜[30]=30日前
hist_date  = ["--/--"] * 31  # 各日の日付文字列
mode       = MODE_SIMPLE
groups     = [g0, g1, g2, g3]
current_rot = display.rotation
rot_t       = time.monotonic()
btn_prev       = True
btn_down_t     = 0.0
btn_long_fired = False
brightness_idx = 0

# 履歴リクエスト状態（逐次方式: 既存子機と同じ）
hist_day  = 0      # 現在リクエスト中の日（0=今日〜30=30日前）
req_sent  = False  # 送信済みフラグ
req_time  = 0.0    # 最終送信時刻
ind_phase = 0      # インジケーター点滅フェーズ
ind_t     = 0.0    # インジケーター最終更新時刻

# ---- メインループ ----
while True:
    now = time.monotonic()

    # ボタン: 離した瞬間=短押し→ページ切替、押し続け一定時間=長押し→明るさ切替
    btn_cur = _btn.value
    if btn_prev and not btn_cur:
        # 押した瞬間
        btn_down_t = now
        btn_long_fired = False
    elif not btn_prev and not btn_cur and not btn_long_fired and now - btn_down_t > BTN_LONGPRESS_T:
        # 長押し検出
        brightness_idx = (brightness_idx + 1) % len(BRIGHTNESS_LEVELS)
        display.brightness = BRIGHTNESS_LEVELS[brightness_idx]
        btn_long_fired = True
    elif not btn_prev and btn_cur:
        # 離した瞬間（長押し済みならページ切替しない）
        if not btn_long_fired:
            mode = (mode + 1) % 4
            display.root_group = groups[mode]
            if mode == MODE_TODAY:
                draw_today()
            elif mode == MODE_WEEK:
                draw_week_bars()
            elif mode == MODE_MONTH:
                draw_month_bars()
    btn_prev = btn_cur

    # 履歴リクエスト（逐次: 応答を待ってから次の日へ）
    if hist_day <= 30:
        if not req_sent:
            send_req(hist_day)
            req_sent = True
            req_time = now
        elif now - req_time > 30:  # 30秒応答なし → 再送
            req_sent = False

    # 受信処理
    packet = e.read()
    if packet is not None:
        try:
            raw = packet.msg
            if len(raw) >= 6 and raw[:2] == b"M:":
                key  = raw[2:6]
                body = raw[6:]

                if key == b"INST":
                    w, a     = body.decode("utf-8").split("/")
                    wattage  = int(w)
                    amperage = float(a)
                    col = watt_color(wattage, amperage)
                    g0_watt.color = col; g0_watt.text = str(wattage)
                    g1_watt.color = col; g1_watt.text = str(wattage)

                elif key[:2] == b"ID":
                    day_id = int(key[2:4].decode())
                    if len(body) < 202:
                        print(f"[RECV] ID{day_id:02d} too short {len(body)}")
                    elif day_id != hist_day:
                        print(f"[RECV] ID{day_id:02d} mismatch hist_day={hist_day}")
                    else:
                        # 日付文字列
                        date_str = body[-202:-197].decode("utf-8", "ignore").strip()
                        hist_date[day_id] = date_str
                        parts = date_str.split("/")
                        if day_id < len(g2_date):
                            if day_id == 0:
                                g2_date[0].text = "TD"
                            elif len(parts) == 2:
                                g2_date[day_id].text = parts[1]
                            else:
                                g2_date[day_id].text = date_str[:2]

                        # バイナリ履歴データ（array.array で省メモリ）
                        bin_data = body[-197:-1]
                        vals = array.array("I", [
                            struct.unpack(">I", bin_data[i*4:i*4+4])[0]
                            for i in range(49)])

                        if vals[0] == 0:
                            print(f"[HIST] ID{day_id:02d} {date_str} skip (base=0)")
                        else:
                            hist_week[day_id] = vals
                            daily_kwh = max(0, vals[48] - vals[0]) * UNIT
                            print(f"[HIST] ID{day_id:02d} {date_str} {daily_kwh:.1f}kWh [0]={vals[0]} [48]={vals[48]}")

                        hist_day += 1
                        req_sent = False
                        if mode == MODE_TODAY:
                            draw_today()
                        elif mode == MODE_WEEK:
                            draw_week_bars()
                        elif mode == MODE_MONTH:
                            draw_month_bars()

                        if hist_day == 31:
                            print("[HIST] 30日分取得完了 ---- 日次一覧 ----")
                            for d in range(31):
                                if hist_week[d] is not None:
                                    kwh = max(0, hist_week[d][48] - hist_week[d][0]) * UNIT
                                    print(f"  [{d:2d}] {hist_date[d]} {kwh:.1f}kWh [0]={hist_week[d][0]} [48]={hist_week[d][48]}")

                elif key == b"CUML":
                    # M5Stack版と同じ日またぎロジック
                    cuml_parts = body.decode("utf-8").strip().split("/")
                    if len(cuml_parts) >= 3:
                        created = cuml_parts[1].strip()        # "2026/06/17 14:30:xx"
                        created_date = created.split(" ")[0]   # "2026/06/17"
                        created_time = created.split(" ")[1][:5]  # "14:30"
                        e_energy = float(cuml_parts[2])

                        if len(cuml_parts) >= 5:
                            monthly_kwh = int(float(cuml_parts[3]))
                            charge_yen  = int(float(cuml_parts[4]))
                            g0_cuml_kwh_val.text = str(monthly_kwh)
                            g0_cuml_yen_val.text = str(charge_yen)
                            collect_date = cuml_parts[0].strip().split(" ")[0]  # "2026-05-23"
                            g0_period.text = f"{collect_date[5:]}~{created_date[5:]}"

                        hh, mm = int(created_time[:2]), int(created_time[3:5])
                        slot_idx = hh * 2 + (1 if mm >= 30 else 0)  # 0=00:00 .. 48=24:00

                        if hist_week[0] is None:
                            hist_week[0] = array.array("I", [0] * 49)

                        raw_val = int(e_energy / UNIT)

                        if slot_idx == 0:
                            # 00:00 = 前日24:00
                            hist_week[0][48] = raw_val
                            print(f"[CUML] {created_time} slot48={raw_val}")
                        else:
                            # 00:30かつslot[2]!=0 → 日またぎ（新しい日が始まっている）
                            if slot_idx == 1 and hist_week[0][2] != 0:
                                print("[CUML] 日またぎ処理")
                                for d in range(30, 0, -1):
                                    hist_week[d] = hist_week[d - 1]
                                    hist_date[d] = hist_date[d - 1]
                                hist_week[0] = array.array("I", [0] * 49)
                                hist_date[0] = created_date[5:]  # "MM/DD"
                                hist_week[0][0] = hist_week[1][48]  # 前日24:00 → 当日00:00
                                for i in range(min(8, 31)):
                                    if i == 0:
                                        g2_date[0].text = "TD"
                                    elif i < len(g2_date):
                                        p = hist_date[i].split("/")
                                        g2_date[i].text = p[1] if len(p) == 2 else hist_date[i][:2]

                            hist_week[0][slot_idx] = raw_val
                            print(f"[CUML] {created_time} slot{slot_idx}={raw_val}")

                        if mode == MODE_TODAY:
                            draw_today()
                        elif mode == MODE_WEEK:
                            draw_week_bars()
                        elif mode == MODE_MONTH:
                            draw_month_bars()

                else:
                    print(f"[RECV] key={key} len={len(raw)}")

        except Exception as ex:
            print(f"[ERR] {ex}")

    # 取得インジケーター（取得中: 赤点滅 / 完了: 青点灯）
    if hist_day <= 30:
        if now - ind_t >= 0.5:
            ind_t = now
            ind_pal[1] = COLOR_WARN if (ind_phase % 2 == 0) else BG_COLOR
            ind_phase += 1
    elif ind_pal[1] != COLOR_MID:
        ind_pal[1] = COLOR_MID

    # 0.5秒ごとに回転チェック
    if now - rot_t >= 0.5:
        rot_t = now
        try:
            ax, ay, _ = read_accel()
            new_rot = accel_to_rotation(ax, ay)
            if new_rot != current_rot:
                display.rotation = new_rot
                current_rot = new_rot
        except Exception:
            pass

    time.sleep(0.05)
