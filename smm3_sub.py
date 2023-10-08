from m5stack import lcd, speaker, btnA, btnB, btnC
from machine import Timer
import _thread
import binascii
import espnow
import math
import ntptime
import utime
import wifiCfg
import gc
import machine
import logging
import func_sub as cnfg
from func_sub import beep, status

# 定数初期値 : 優先順位　 　設定GSS > 設定ファイル > 初期値
config = {
    'WARNING_AMPERAGE': 30,   # 警告アンペア(A)
    'LCD_BRIGHTNESS': 15,     # 画面の明るさ(0〜255)
    'BG_COLOR': 0x102030,     # 背景色(RGB)
    'ROTATION_INTERVAL': 15,  # オートローテーション間隔(秒)
    'DAY_GRAPH_SCALE': 1.0,   # 当日・前日比較グラフ：縦軸(kWh)
    'TH_WARNING': 0.6,        # 当日・前日比較グラフ：警告域(kWh)
    'TH_ADVISORY': 0.3,       # 当日・前日比較グラフ：予告域(kWh)
    'GRAPH_SCALE': 25,        # 7,30日クラフ:横軸(kWh)
    'TIMEOUT_SUB': 60,        # 親機＞子機タイムアウト(秒)
    'LOG_LEVEL': 'INFO',  # 'CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'
    'UNIT': 0.1,              # 積算電力量[単位x係数]
}

logger_name = 'SUB'

# 表示モード関係
inst_mode = 'timeout'
beep_on = True
step = 0
page = 0
auto_rotation_sw = False  # オートローテーションのスイッチ

# タイマー
rotation_timer = Timer(0)
indicator_timer = Timer(3)

# 履歴データを取得する期間（日）
data_period = 30

# # Colormap (tab10)
# colormap = (
#     0x1f77b4,  # tab0:blue
#     0xff7f0e,  # tab1:orange
#     0x2ca02c,  # tab2:green
#     0xd62728,  # tab3:red
#     0x9467bd,  # tab4:purple
#     0x8c564b,  # tab5:brown
#     0xe377c2,  # tab6:pink
#     0x7f7f7f,  # tab7:gray
#     0xbcbd22,  # tab8:olive
#     0x17becf,  # tab9:cyan
#     )

# 表示色設定
uncolor = 0xa0a0a0    # Unit color
tx_color1 = 0xc0c0c0  # Text 1 color
tx_color2 = 0xefefef  # Text 2 color
color1 = 0x1f77b4     # Current value color
color2 = 0xe08040     # Total value color
color3 = 0xd62728     # Limit over color
grayout = 0x303030
yellow = 0x404000

# 時間帯インデックス(30分毎：0〜47)
TIME_TB = [
    "00:00", "00:30",
    "01:00", "01:30",
    "02:00", "02:30",
    "03:00", "03:30",
    "04:00", "04:30",
    "05:00", "05:30",
    "06:00", "06:30",
    "07:00", "07:30",
    "08:00", "08:30",
    "09:00", "09:30",
    "10:00", "10:30",
    "11:00", "11:30",
    "12:00", "12:30",
    "13:00", "13:30",
    "14:00", "14:30",
    "15:00", "15:30",
    "16:00", "16:30",
    "17:00", "17:30",
    "18:00", "18:30",
    "19:00", "19:30",
    "20:00", "20:30",
    "21:00", "21:30",
    "22:00", "22:30",
    "23:00", "23:30",
]


# 【calc】　today[yyyy-mm-dd] から days日前の日付[MM/DD]を返す
def date_of_days_ago(today, days):
    year = int(today[:4])
    month = int(today[5:7])
    date = int(today[8:10])
    t = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
        t = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)  # うるう年

    days_of_year = sum(t[:month - 1]) + date

    ago_date = days_of_year - days
    if ago_date > 0:
        ago_month = 1
        while ago_date > t[ago_month - 1]:
            ago_date -= t[ago_month - 1]
            ago_month += 1
    else:
        ago_month = 12
        ago_date = ago_date + 31

    return '{:d}/{:d}'.format(ago_month, ago_date)


# 【exec】　BEEP音鳴らしスレッド関数
def beep_sound():
    while True:
        if inst_mode != 'good':  # タイムアウトで表示ミュートされてるか、初期値のままならpass
            pass
        else:  # 警告閾値超えでBEEP ONなら
            if (amperage >= config['WARNING_AMPERAGE']) and (beep_on is True):
                speaker.tone(freq=220, duration=200)
                utime.sleep(2)
        utime.sleep(0.1)


# 【exec】　擬似Boldタイプ文字表示
def print_b(text, x, y, col, w):
    for n in range(0, w):
        lcd.print(text, x + n, y, color=col)


# 【exec】　ページめくり処理スレッド関数
def flip_page(direction):
    global page

    # ボタンが押されるたびにページを進める/戻す
    page = page + direction
    if page == len(draw_page):
        page = 0
    elif page == -1:
        page = len(draw_page) - 1

    # ボタンエリア以外は一旦画面全消し
    lcd.rect(0, 0, 320, 224, BG_COLOR, BG_COLOR)

    # 当該ページを表示
    draw_page[page]()

    # オートローテーションのタイマーをリセット
    if auto_rotation_sw is True:
        rotation_timer.deinit()
        rotation_timer.init(period=int(config['ROTATION_INTERVAL'] * 1000),
                            mode=rotation_timer.PERIODIC, callback=lambda t: flip_page(direction))

    utime.sleep(0.1)


# 【exec】　オートローテーション
def auto_rotation(direction):
    global auto_rotation_sw

    if auto_rotation_sw is False:  # スタート
        rotation_timer.init(period=int(config['ROTATION_INTERVAL'] * 1000),
                            mode=rotation_timer.PERIODIC, callback=lambda t: flip_page(direction))
        logger.info('[EXEC] auto_rotation on')
        auto_rotation_sw = True
    else:  # ストップ
        rotation_timer.deinit()
        logger.info('[EXEC] auto_rotation off')
        auto_rotation_sw = False

    draw_cumul()
    beep()


# 【exec】　画面初期化
def init_screen():
    lcd.setBrightness(0)  # バックライトOFF
    lcd.setColor(bcolor=BG_COLOR)
    lcd.clear()
    lcd.rect(0, 224, 320, 240, 0x303030, 0x303030)
    draw_page[page]()
    draw_beep_icon(False)
    draw_cumul()
    if sum(hist_flag) == data_period + 1:
        lcd.circle(310, 232, 8, 0x1f77b4, 0x1f77b4)
    lcd.setBrightness(config['LCD_BRIGHTNESS'])  # バックライト輝度設定
    logger.info('[INIT] Screen init OK')


# 【draw】　BEEPアイコン描画
def draw_beep_icon(flip):
    global beep_on
    if flip is True:
        beep_on = not (beep_on)
    if beep_on is True:   # BEEP ON
        col1 = 0x1f77b4
        col2 = 0x1f77b4
        col3 = 0xd0d0d0
    else:              # BEEP OFF
        col1 = 0x202020
        col2 = 0x404040
        col3 = 0x202020

    lcd.roundrect(230, 225, 58, 15, 7, col1, col2)
    lcd.font(lcd.FONT_Default)
    lcd.print("BEEP", 242, 227, col3)


# 【draw】　データ受信インジケーター描画
def draw_indicator(timer):
    global step
    rad = 2 * math.pi * (step / 15)
    vol = ((1 - math.cos(rad)) / 2 * (0xff - 0x30)) + 0x30
    col = int('0x' + '{:x}'.format(round(vol * 0.9)) + '3030', 16)
    # # 背景黒(0x000000)の場合の例
    # vol = (1 -math.cos(rad)) / 2 * 0xff
    # col = int('0x' + '{:x}'.format(round(vol * 0.9)) + '0000', 16)
    lcd.circle(310, 232, 8, col, col)
    step += 1


# 【draw】　積算電力量の最終受信日付表示
def draw_cumul():
    if auto_rotation_sw is True:  # オートローテーションの状態によって色を変える
        col = 0x808010
    else:
        col = 0x1f77b4
    lcd.rect(0, 224, 229, 240, 0x303030, 0x303030)
    lcd.font(lcd.FONT_Default)
    if cumul_date == '':
        lcd.print('****-**-** **:**', 2, 227, col)
    else:
        lcd.print(cumul_date + ' ' + cumul_time, 2, 227, col)


# 【page】　メインページ：瞬間電力値、検針日以降の電力量、電気代
def draw_main():
    # 瞬間電力値の表示
    draw_w_a()

    # 今月（検針日を起点）の日付範囲を表示
    (x, y, w, h) = (0, 125, 320, 25)
    lcd.rect(x, y, w, h, BG_COLOR, BG_COLOR)
    s = '{}~{}'.format(collect[5:10], created[5:10])
    lcd.font(lcd.FONT_DejaVu24)
    lcd.print(s, lcd.CENTER, y, uncolor)

    # 今月（検針日を起点）の電力量の表示
    (x, y, w, h) = (0, 150, 140, 40)
    lcd.rect(x, y, w, h, BG_COLOR, BG_COLOR)
    if e_energy == 0:
        e_energy_d = '-'
    else:
        e_energy_d = str(int(e_energy))
    lcd.font(lcd.FONT_DejaVu40)
    len_txt = lcd.textWidth(e_energy_d)
    lcd.print(e_energy_d, x + w - len_txt - 20, y + 5, color2)

    # 今月（検針日を起点）の電気料金の表示
    (x, y, w, h) = (140, 150, 180, 40)
    lcd.rect(x, y, w, h, BG_COLOR, BG_COLOR)
    if charge == 0:
        charge_d = '-'
    else:
        charge_d = str(int(charge))
    lcd.font(lcd.FONT_DejaVu40)
    len_txt = lcd.textWidth(charge_d)
    lcd.print(charge_d, x + w - len_txt - 20, y + 5, color2)

    # 単位表示
    (x, y, w, h) = (0, 190, 320, 34)
    lcd.rect(x, y, w, h, BG_COLOR, BG_COLOR)
    lcd.font(lcd.FONT_DejaVu24)
    lcd.print('kWh', 80, 195, uncolor)
    lcd.print('Yen', 265, 195, uncolor)


# 【page】　瞬間電力値の表示
def draw_w_a():
    # 表示文字色の設定
    if inst_mode == 'timeout':  # 親機〜スマートメーター間タイムアウト：淡黄色文字
        fc = yellow
    elif inst_mode == 'lost':  # 子機〜親機間タイムアウト：グレー文字
        fc = grayout
    elif inst_mode == 'good':  # 通常受信状態
        if amperage >= config['WARNING_AMPERAGE']:  # 警告アンペア超時：指定色
            fc = color3
        else:  # 通常時:指定色
            fc = color1

    # 瞬間電力値最大化表示モード時
    if draw_page[page] == draw_main:
        lcd.rect(0, 0, 320, 125, BG_COLOR, BG_COLOR)
        # 瞬間電力値表示
        lcd.font(lcd.FONT_7seg, dist=30, width=6)
        lcd.print(str(wattage) + ' ', lcd.RIGHT, 10, fc)
        # W表示
        lcd.font(lcd.FONT_DejaVu40)
        lcd.print('W', 274, 78, uncolor)
        # 瞬間電流表示
        lcd.font(lcd.FONT_DejaVu24)
        lcd.print(str(int(amperage)), 300 - lcd.textWidth(str(int(amperage))), 54, fc)
        lcd.font(lcd.FONT_Ubuntu)
        lcd.print('A', 303, 59, uncolor)

    # 電力量グラフ (当日と前日) 表示モード時
    elif draw_page[page] == draw_graph_1:
        lcd.rect(70, 0, 250, 63, BG_COLOR, BG_COLOR)
        # 瞬間電力値表示
        lcd.font(lcd.FONT_7seg, dist=14, width=3)
        lcd.print(str(wattage) + '   ', lcd.RIGHT, 7, fc)
        # W表示
        lcd.font(lcd.FONT_DejaVu24)
        lcd.print('W', 240, 32, uncolor)
        # 瞬間電流表示
        lcd.font(lcd.FONT_DejaVu24)
        lcd.print(str(int(amperage)), 300 - lcd.textWidth(str(int(amperage))), 37, fc)
        lcd.font(lcd.FONT_Ubuntu)
        lcd.print('A', 303, 42, uncolor)


# 【page】　電力量グラフ (当日と前日・30分毎)
def draw_graph_1():
    graph_max = 140             # グラフ高さ
    width = 5                   # バーの幅
    interval = 1                # バーの描画間隔
    color_today = 0x000000      # 初期値 = 黒色
    color_yesterday = 0x404060  # 前日のグラフ描画色 = グレー
    color_delta = 0xf04040      # 前日からの増分のグラフ描画色 = 赤

    # 瞬間電力値の表示
    draw_w_a()

    # グリッド描画
    lcd.rect(0, 65, 320, 159, BG_COLOR, BG_COLOR)
    lcd.line(0, 64, 320, 64, 0xaeaeae)
    lcd.line(0, 206, 320, 206, 0xaeaeae)
    for i in range(0, 49, 12):
        lcd.line(6 * i + 15, 65, 6 * i + 15, 206, 0x303030)

    lcd.font(lcd.FONT_Ubuntu)
    for i in range(0, 5):
        lcd.print('{:02}'.format(i * 6), i * 72 + 6, 208, tx_color1)
    print_b('{:.1f} kWh'.format(DAY_GRAPH_SCALE), 0, 48, tx_color1, 2)

    # グラフ描画メイン
    for n in range(0, 48):  # 毎30分 x 48
        # 前日のグラフ高さの計算
        if (hist_data[1][n + 1] == 0) or (hist_data[1][n] == 0):
            h_power_yesterday = 0
        else:
            h_power_yesterday = round((hist_data[1][n + 1] - hist_data[1][n]) / 1000, 1)

        if h_power_yesterday <= 0:  # マイナス値は有り得ないが念のため
            height_yesterday = 0
        else:
            height_yesterday = int(h_power_yesterday * graph_max / DAY_GRAPH_SCALE)

        if height_yesterday > graph_max:  # graph_maxを超えた値はgraph_maxに丸める
            height_yesterday = graph_max

        # 当日のグラフ高さの計算
        if (hist_data[0][n + 1] == 0) or (hist_data[0][n] == 0):
            h_power_today = 0
        else:
            h_power_today = round((hist_data[0][n + 1] - hist_data[0][n]) / 1000, 1)

        if h_power_today <= 0:  # マイナス値は有り得ないが念のため
            height_today = 0
        else:
            height_today = int(h_power_today * graph_max / DAY_GRAPH_SCALE)

        if height_today > graph_max:  # graph_maxを超えた値はgraph_maxに丸める
            height_today = graph_max

        if ((height_today == 0) or (height_yesterday == 0) or (height_today <= height_yesterday)):
            height_today_delta = 0
            height_today_base = height_today
        else:
            height_today_delta = height_today - height_yesterday
            height_today_base = height_yesterday

        # グラフ高さに応じて色指定
        if h_power_today > config['TH_WARNING']:     # 警告域を越えたら橙色
            color_today = 0xee8040
        elif h_power_today > config['TH_ADVISORY']:  # 予告域を越えたら黃色
            color_today = 0xeed070
        else:                                        # 通常域は青色
            color_today = 0x19758d

        x_start = (n * (width + interval)) + 16  # バーの描画開始位置

        # グラフ描画セクション
        if height_yesterday != 0:  # 前日のバー描画
            lcd.rect(x_start, 205 - height_yesterday, width,
                     height_yesterday, color_yesterday, color_yesterday)
        if height_today_base != 0:  # 当日のバー描画
            lcd.rect(x_start, 205 - height_today_base, width,
                     height_today_base, color_today, color_today)
        if height_today_delta != 0:  # 前日と当日の差分バー描画
            lcd.rect(x_start, 205 - height_today, width,
                     height_today_delta, color_delta, color_delta)


# 【page】　電力量グラフ (直近7日間) 表示
def draw_graph_7():
    draw_period = 7
    bar_width = 20
    bar_pitch = 25
    gr_start = 25
    av_start = 200

    draw_graph(draw_period, bar_width, bar_pitch, gr_start, av_start)


# 【page】　電力量グラフ (直近30日間) 表示
def draw_graph_30():
    draw_period = 30
    bar_width = 7
    bar_pitch = 6
    gr_start = 23
    av_start = 213

    draw_graph(draw_period, bar_width, bar_pitch, gr_start, av_start)


# 【page】　電力量グラフ (随時比較・当日と直近[draw_period]日間)
def draw_graph(draw_period, bar_width, bar_pitch, gr_start, av_start):
    # draw_period  # グラフ描画の日数
    # bar_width    # グラフの幅
    # bar_pitch    # グラフのピッチ
    # gr_start     # 過去グラフのスタート位置(Y)
    # av_start     # 平均グラフのスタート位置(Y)

    today_sub_t = 0                        # 当日の現在時刻までの小計
    daily_sub_t = [0] * (draw_period + 1)  # 履歴の現在時刻までの小計
    daily_cumul = [0] * (draw_period + 1)  # 履歴の終日合計
    avg_sub_t = 0                          # 平均の現在時刻までの小計
    avg_cumul = 0                          # 平均の終日合計

    if cumul_time:
        # データ集計セクション
        if TIME_TB.index(cumul_time) == 0:
            index = 48
        else:
            index = TIME_TB.index(cumul_time)

        if hist_data[0][0]:
            today_sub_t = round((hist_data[0][index] - hist_data[0][0]) / 1000, 1)

        for n in range(1, draw_period + 1):
            if hist_data[n][0]:
                daily_sub_t[n] = round((hist_data[n][index] - hist_data[n][0]) / 1000, 1)
                daily_cumul[n] = round((hist_data[n][48] - hist_data[n][0]) / 1000, 1)

        avg_period = sum(hist_flag) - 1    # データ取得完了前の場合は、取得日までの平均を算出する

        if avg_period > 0:
            if avg_period > draw_period:
                avg_period = draw_period
            avg_sub_t = round(sum(daily_sub_t) / avg_period, 1)
            avg_cumul = round(sum(daily_cumul) / avg_period, 1)

        # 画面初期化・グリッド描画
        lcd.rect(0, 0, 320, 224, BG_COLOR, BG_COLOR)
        if draw_period == 30:
            for y in range(22, 200, 44):
                lcd.line(0, y, 320, y, 0x303030)
            lcd.line(0, 212, 320, 212, 0x303030)

        # グラフ描画セクション
        if hist_data[draw_period][0] and today_sub_t > avg_sub_t:
            color_fill = 0x800000
            color_edge = 0xd00000
        else:
            color_fill = 0x2c802c
            color_edge = 0x2cd02c

        today_len_sub_t = int(320 * (today_sub_t / GRAPH_SCALE))
        lcd.rect(0, 0, today_len_sub_t, 20, color_edge, color_fill)

        for i in range(0, draw_period // 7 + 1):
            for j in range(1, 8):
                n = i * 7 + j
                if n <= draw_period:
                    y = (n - 1) * bar_pitch + i * 2 + gr_start
                    len_sub_t = int(320 * (daily_sub_t[n] / GRAPH_SCALE))
                    len_cumul = int(320 * (daily_cumul[n] / GRAPH_SCALE))
                    lcd.rect(0, y, len_cumul, bar_width, 0x0095ad, 0x104040)
                    lcd.rect(0, y, len_sub_t, bar_width, 0x0095ad, 0x19758d)

        len_sub_t = int(320 * (avg_sub_t / GRAPH_SCALE))
        len_cumul = int(320 * (avg_cumul / GRAPH_SCALE))
        lcd.rect(0, av_start, len_cumul, bar_width, 0x0095AD, 0x104040)
        lcd.rect(0, av_start, len_sub_t, bar_width, 0x0095AD, 0x0000a0)

        x = today_len_sub_t - 1
        lcd.line(x, 0, x, 219, color_edge)
        lcd.line(x - 1, 21, x - 1, 219, BG_COLOR)
        lcd.triangle(x, 219, x + 4, 223, x - 4, 223, color_edge, color_edge)

        # 文字描画セクション
        lcd.font(lcd.FONT_Ubuntu)

        max_txt = str(GRAPH_SCALE) + ' kWh >'
        t_sub_t = '{:.1f} kWh'.format(today_sub_t)
        print_b(max_txt, 318 - lcd.textWidth(max_txt), 0 + 3, tx_color2, 2)
        print_b(' Today :', 5, 0 + 3, tx_color2, 2)
        print_b(t_sub_t, 145 - lcd.textWidth(t_sub_t), 0 + 3, tx_color2, 2)

        a_sub_t = '{:.1f}'.format(avg_sub_t)
        a_cumul = '{:.1f}'.format(avg_cumul)
        print_b(' AVG :', 19, 200 + 3, tx_color2, 2)
        print_b(a_sub_t, 107 - lcd.textWidth(a_sub_t), 200 + 3, tx_color2, 2)
        print_b(a_cumul, 153 - lcd.textWidth(a_sub_t), 200 + 3, tx_color2, 2)

        # 7日間グラフの場合は日毎データ値を表示
        if draw_period == 7:
            for n in range(1, avg_period + 1):
                d_date = hist_date[n] + ' :'
                d_sub_t = '{:.1f}'.format(daily_sub_t[n])
                d_cumul = '{:.1f}'.format(daily_cumul[n])
                y = (n * 25) + 3
                lcd.print(d_date, 68 - lcd.textWidth(d_date), y, color=tx_color1)
                lcd.print(d_sub_t, 107 - lcd.textWidth(d_sub_t), y, color=tx_color1)
                lcd.print(d_cumul, 153 - lcd.textWidth(d_cumul), y, color=tx_color1)

    else:
        lcd.rect(0, 0, 320, 224, BG_COLOR, BG_COLOR)
        lcd.font(lcd.FONT_DejaVu18)
        lcd.println('Please wait a moment.', 50, lcd.CENTER, color=uncolor)

    del avg_sub_t, avg_cumul
    gc.collect()


# 【page】　＜前日＞との積算電力量比較表 表示
def draw_table_1():
    draw_table(1, 'Ytdy', 0xff8000)


# 【page】　＜直近7日間＞との積算電力量比較 表示
def draw_table_7():
    draw_table(7, 'Avg7', 0x1f77b4)


# 【page】　＜直近30日間＞との積算電力量比較 表示
def draw_table_30():
    draw_table(30, 'Avg30', 0x2ca02c)


# 【page】　積算電力量比較 (当日と期間(calc_period)平均・1時間毎)
def draw_table(calc_period, caption, col_caption):
    # calc_period       集計期間（30日以内）
    # caption           キャプション（5文字以下）
    # col_caption       キャプションの色

    # データ初期化  hour_power : 24時間x(計算期間 + 当日）
    hour_power = [[0 for i in range(24)] for j in range(calc_period + 1)]
    avg_hour_power = [0] * 24

    # 描画エリアのクリアとタイトル表示
    lcd.rect(0, 0, 320, 224, BG_COLOR, BG_COLOR)
    lcd.font(lcd.FONT_Ubuntu)
    print_b('AM: Tdy:{:6}Diff'.format(caption + ':'), 0, 0, col_caption, 2)
    print_b('PM: Tdy:{:6}Diff'.format(caption + ':'), 166, 0, col_caption, 2)
    lcd.print('|' + '\n', 155, 0, color=tx_color1)

    # データ集計セクション
    for n in range(0, 12):  # 0〜11
        nn = n * 2  # 元データが30分毎なのでステップを倍に
        for i in range(0, calc_period + 1):     # i=0 当日, i=n n日前
            if (hist_data[i][nn + 2] == 0) or (hist_data[i][nn] == 0):
                hour_power[i][n] = 0
            else:  # 1時間あたりの定時積算電力量（単位：kWh）
                hour_power[i][n] = round((hist_data[i][nn + 2] - hist_data[i][nn]) / 1000, 1)

            if ((hist_data[i][nn + 24 + 2] == 0) or (hist_data[i][nn + 24] == 0)):
                hour_power[i][n + 12] = 0
            else:  # 1時間あたりの定時積算電力量（単位：kWh）
                hour_power[i][n + 12] = round((hist_data[i][nn + 24 + 2]
                                               - hist_data[i][nn + 24]) / 1000, 1)

    avg_period = sum(hist_flag) - 1  # データ取得完了前の場合は、取得日までの平均を算出する

    if avg_period > 0:
        if avg_period > calc_period:
            avg_period = calc_period
        for n in range(0, 24):
            sum_of_hour_power = 0
            for i in range(1, calc_period + 1):
                sum_of_hour_power += hour_power[i][n]
            avg_hour_power[n] = round(sum_of_hour_power / avg_period, 1)

    for n in range(0, 12):  # 0〜11
        # 期間平均同時刻との差分
        if (hour_power[0][n] == 0) or (avg_hour_power[n] == 0):
            # 期間平均か当日が0なら差分0
            diff_AM = 0
            diff_AM_str = '--- '
        else:
            diff_AM = hour_power[0][n] - avg_hour_power[n]
            diff_AM_str = '{:3.1f}'.format(diff_AM)

        if (hour_power[0][n + 12] == 0) or (avg_hour_power[n + 12] == 0):
            # 期間平均か当日が0なら差分0
            diff_PM = 0
            diff_PM_str = '--- '
        else:
            diff_PM = hour_power[0][n + 12] - avg_hour_power[n + 12]
            diff_PM_str = '{:3.1f}\n'.format(diff_PM)

        # 電力量が期間平均を超えていたら赤文字、期間平均以下なら緑文字
        if diff_AM > 0:
            color_diff_AM = 0xd00000  # 赤
        else:
            color_diff_AM = 0x00d000  # 緑
        if diff_PM > 0:
            color_diff_PM = 0xd00000  # 赤
        else:
            color_diff_PM = 0x00d000  # 緑

        # 描画セクション
        lcd.print(' {:02}: '.format(n), color=0xd0d000)
        lcd.print(' {:3.1f}:  {:3.1f}: '.format(hour_power[0][n],
                  avg_hour_power[n]), color=tx_color1)
        lcd.print(diff_AM_str, 149 - lcd.textWidth(diff_AM_str), (n + 1) * 16, color=color_diff_AM)
        lcd.print(' |  ', color=tx_color1)
        lcd.print('{:02}: '.format(n + 12), color=0xd0d000)
        lcd.print(' {:3.1f}:  {:3.1f}: '.format(hour_power[0][n + 12],
                  avg_hour_power[n + 12]), color=tx_color1)
        lcd.print(diff_PM_str, 315 - lcd.textWidth(diff_PM_str), (n + 1) * 16, color=color_diff_PM)

    # 当日(現時刻まで)および期間平均の24時間積算電力量と、比(%)を最下段に表示
    if cumul_time:
        if TIME_TB.index(cumul_time) == 0:
            index = 24
        else:
            index = int(TIME_TB.index(cumul_time) / 2)

        hist_data_of_avg = 0
        hist_data_of_Today = 0

        for n in range(index):
            hist_data_of_avg += avg_hour_power[n]
            hist_data_of_Today += hour_power[0][n]
        if hist_data_of_avg != 0:
            _Ratio = round((hist_data_of_Today / hist_data_of_avg) * 100)
            hist_data_Ratio = str(_Ratio) + '%'
            if _Ratio > 100:
                color_ratio = 0xd00000  # 赤
            else:
                color_ratio = 0x00d000  # 緑
        else:
            hist_data_Ratio = 'N/A'
            color_ratio = tx_color1

        hist_data_of_avg = '{:.1f}'.format(hist_data_of_avg)
        hist_data_of_Today = '{:.1f}'.format(hist_data_of_Today)

        caption_t = caption + 'Total:'
        lcd.font(lcd.FONT_Default)
        lcd.print('TdyTotal:', 0, 211, color=col_caption)
        lcd.print(caption_t, 192 - lcd.textWidth(caption_t), 211, color=col_caption)
        lcd.print('Ratio:', 233, 211, color=col_caption)

        lcd.font(lcd.FONT_Ubuntu)
        lcd.print(hist_data_of_Today, 67, 208, color=0xffffff)
        lcd.print(hist_data_of_avg, 193, 208, color=0xffffff)
        lcd.print(hist_data_Ratio, 274, 208, color=color_ratio)

    del hour_power, avg_hour_power
    gc.collect()


# 【config】　設定用GSSから設定をリロード
def reload_config(config):
    global DAY_GRAPH_SCALE, GRAPH_SCALE, BG_COLOR, unit

    lcd.clear()
    lcd.font(lcd.FONT_DejaVu18)
    lcd.println('Config_GSS reloading.', 0, 0, color=0xFFFFFF)

    config = cnfg.update_config_from_gss(api_config, config)
    cnfg.save_config(config)
    DAY_GRAPH_SCALE, GRAPH_SCALE, BG_COLOR, unit = cnfg.set_config(config)

    log_level = getattr(logging, config['LOG_LEVEL'], None)
    logging.basicConfig(level=log_level)
    logger.info('[INIT] Logging level = %s', config['LOG_LEVEL'])

    init_screen()
    beep()


# 【exec】　積算電力-履歴データ取得
def get_hist_data():
    global hist_day, hist_flag, hist_date, unit, hist_data, day_shift

    logger.info('[INIT] Get Historical DATA')

    hist_day = 0
    hist_flag = [False] * (data_period + 1)
    hist_date = ['**/**'] * (data_period + 1)
    hist_data = [[0 for i in range(49)] for j in range(data_period + 1)]
    day_shift = 0

    # unit = None  # << unut*coefficient を取得する場合

    init_screen()
    indicator_timer.deinit()
    indicator_timer.init(period=200, mode=indicator_timer.PERIODIC, callback=draw_indicator)
    beep()


if __name__ == '__main__':

    try:
        # logger 初期化
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(logger_name)

        # WiFi & ESP-NOW 設定
        wifiCfg.autoConnect(lcdShow=True)
        wifiCfg.wlan_ap.active(True)
        espnow.init(0)

        lcd.clear()
        lcd.println('Welcome to SMM3 !', 0, 0, color=0xFFFFFF)

        # 定数の読み込み（ファイル、Googleスプレッドシート）
        config = cnfg.update_config_from_file(config)
        api_config = cnfg.get_api_config()
        config = cnfg.update_config_from_gss(api_config, config)
        cnfg.save_config(config)
        DAY_GRAPH_SCALE, GRAPH_SCALE, BG_COLOR, unit = cnfg.set_config(config)

        log_level = getattr(logging, config['LOG_LEVEL'], None)
        logging.basicConfig(level=log_level)
        logger.info('[INIT] Logging level = %s', config['LOG_LEVEL'])

        # RTC設定（時刻設定）
        ntp = ntptime.client(host='jp.pool.ntp.org', timezone=9)
        status('RTC init OK.')

        # ページ設定
        draw_page = [
            draw_main,      # メインページ：瞬間電力値、検針日以降の電力量、電気代
            draw_graph_1,   # 電力量グラフ (当日と前日・30分毎)
            draw_table_1,   # 積算電力量比較表 (当日と前日・1時間毎)
            draw_graph_7,   # 電力量グラフ (随時比較・当日と直近7日間)
            draw_table_7,   # 積算電力量比較表 (当日と直近7日間平均・1時間毎)
            draw_graph_30,  # 電力量グラフ (随時比較・当日と直近30日間)
            draw_table_30   # 積算電力量比較表 (当日と直近30日間平均・1時間毎)
        ]

        # ボタン検出スレッド起動
        # Aボタン       ページ進む
        # Bボタン       ページ戻る
        # Cボタン       警告beep on/off
        # Aボタン長押し  GSS から config リロード
        # Bボタン長押し  オートローテーション on/off
        # Cボタン長押し  履歴データ再取得

        btnA.wasReleased(lambda direction=-1: flip_page(direction))
        btnB.wasReleased(lambda direction=1: flip_page(direction))
        btnC.wasReleased(lambda flip=True: draw_beep_icon(flip))
        btnA.pressFor(0.8, lambda config=config: reload_config(config))
        btnB.pressFor(0.8, lambda direction=1: auto_rotation(direction))
        btnC.pressFor(0.8, get_hist_data)
        status('Button thread start.')

        utime.sleep(5)

        # データ取得処理
        hist_day = 0
        hist_flag = [False] * (data_period + 1)
        hist_date = ['**/**'] * (data_period + 1)
        hist_data = [[0 for i in range(49)] for j in range(data_period + 1)]
        day_shift = 0

        # unitをメーターからの取得値によらず固定としている (unit*coefficient)
        unit = config['UNIT']

        # 表示値初期値
        wattage = 0
        amperage = 0
        e_energy = 0
        charge = 0
        collect = '****-**-**'
        created = '*****-**-**'
        cumul_date = ''
        cumul_time = ''
        data_date = ''
        data_time = ''

        # タイマー処理
        wattage_time = utime.time()

        # BEEP音鳴らしスレッド起動
        _thread.start_new_thread(beep_sound, ())
        status('BEEP thread start.')

        # 画面初期化
        init_screen()
        indicator_timer.deinit()
        indicator_timer.init(period=200, mode=indicator_timer.PERIODIC, callback=draw_indicator)

        # メインループ
        while True:

            # 瞬間電力値の更新が[TIMEOUT_SUB]秒以上途絶えたら、電力値<薄黄色>表示　
            if utime.time() - wattage_time >= config['TIMEOUT_SUB']:
                if inst_mode == 'good':
                    inst_mode = 'lost'
                    draw_w_a()

            # # 'UNIT' 積算電力量-[単位x係数]をリクエスト  << unit*coefficient を取得する場合
            # if unit is None:
            #     espnow.broadcast(data='UNIT')
            #     logger.info('[UNIT] >> Request UNIT')

            # 'REQ' 積算電力量-履歴データをリクエスト
            if (sum(hist_flag) < (data_period + 1)):  # and unit:
                espnow.broadcast(data='REQ' + '{:02}'.format(hist_day))
                logger.debug('[SENT] >> Key = [REQ%2d]', hist_day)

            # # 'UNIT' 積算電力量-[単位x係数]をリクエスト
            # if unit is None:
            #     if request_UNIT is False:
            #         espnow.broadcast(data='UNIT')
            #         logger.info('[UNIT] >> Request UNIT')
            #         request_UNIT = True

            # 親機からデータを受信(ESP NOW)
            d = espnow.recv_data()

            # 受信データ処理
            if (len(d[2]) > 0):
                r_key = str(d[2][:4].decode().strip())  # 先頭4文字が key
                r_data = d[2][4:].strip()

                logger.debug('[RECV] << Key = [%s]', r_key)

                # 親機起動時処理 : 履歴データ再取得
                if r_key == 'BOOT':
                    logger.info('[INIT] Master booted.')
                    get_hist_data()

                # 親機〜スマートメーター間タイムアウト通知受信処理
                elif r_key == 'TOUT':
                    if inst_mode != 'timeout':
                        inst_mode = 'timeout'
                        draw_w_a()

                # # 積算電力量-[単位x係数]受信処理  << unit*coefficient を取得する場合
                # elif r_key == 'UNT=':
                #     unit = float(r_data.decode())
                #     logger.info('[UNIT] << UNIT = %s', unit)
                #     request_UNIT = False

                # 積算電力量-履歴データ受信処理
                elif r_key[:2] == 'ID':
                    id = int(r_key[2:4].strip())
                    d2 = binascii.hexlify(r_data[19:]).decode('utf-8').strip()
                    data_date = r_data[:10].decode('utf-8').strip()
                    data_time = r_data[11:16].decode('utf-8').strip()[:5]

                    if TIME_TB.index(data_time) == 0:  # 履歴データ取得時刻が00:00の場合は基準日を1日シフト
                        day_shift = 1                  # 日跨ぎ処理でシフト解消

                    if (id - day_shift == 0) and cumul_time == '':
                        cumul_date = data_date
                        cumul_time = data_time

                    if (day_shift == 1) and (id == 0) and (hist_day == 0):
                        hist_data[0][48] = int(int(d2[0:8], 16) * unit * 1000)
                        hist_day = 1

                    if (id == hist_day):  # and unit:  # 受信データ = 要求日のデータ なら
                        if hist_flag[id - day_shift] is False:  # 要求日のデータが存在しなければ、受信処理
                            for k in range(0, 48):
                                if int(d2[(k * 8):(k * 8) + 8], 16) > 0x05f5e0ff:  # =99999999
                                    hist_data[id - day_shift][k] = 0
                                else:
                                    hist_data[id - day_shift][k] = int(int(d2[(k*8):(k*8) + 8], 16)
                                                                       * unit * 1000)
                            hist_date[id - day_shift] = date_of_days_ago(data_date, id)
                            hist_flag[id - day_shift] = True
                            if id - day_shift < data_period:
                                hist_data[id - day_shift + 1][48] = hist_data[id - day_shift][0]

                            logger.info('[HIST] << [(%d-%d) %s %s [%s %.1f - %.1f : %.1f]]', 
                                        id, day_shift, data_date, data_time,
                                        hist_date[id - day_shift],
                                        hist_data[id - day_shift][0] / 1000,
                                        hist_data[id - day_shift][47] / 1000,
                                        hist_data[id - day_shift][48] / 1000)
                            logger.debug('[HIST] << Raw = %s', hist_data[id - day_shift])

                            draw_page[page]()  # ページ再描画
                            draw_cumul()

                            if sum(hist_flag) == data_period + 1:
                                beep()
                                indicator_timer.deinit()
                                lcd.circle(310, 232, 8, 0x1f77b4, 0x1f77b4)

                        hist_day += 1

                # 積算電力量受信処理
                elif r_key == 'CUML':
                    cumul_data = r_data.decode().strip().split('/')
                    cumul_wh = int(float(cumul_data[0]) * 1000)  # 積算電力量
                    created = cumul_data[1]
                    cumul_date = created.strip().split(' ')[0]  # 定時積算電力取得日
                    cumul_time = created.strip().split(' ')[1][:5]  # 定時積算電力取得時刻
                    collect = cumul_data[2]  # 直近の検針日時
                    e_energy = float(cumul_data[3])  # 今月の電力量(cumul_dateまで)
                    charge = cumul_data[4]  # 今月の電気料金(cumul_dateまで)

                    logger.info('[CUML] << %s', cumul_data)

                    # 日跨ぎ処理
                    if TIME_TB.index(cumul_time) == 0:
                        hist_data[0][48] = cumul_wh  # 00:00のデータなら、当日24:00のデータとする
                    else:
                        # 00:30のデータ かつ 当日01:00のデータがある（日跨ぎ処理未実施）なら、日跨ぎ処理を行う
                        if (TIME_TB.index(cumul_time) == 1) and (hist_data[0][2] != 0):
                            for id in range(data_period, 0, -1):
                                hist_data[id] = hist_data[id - 1]  # 履歴データシフト
                                hist_date[id] = hist_date[id - 1]  # 履歴日付けシフト
                            hist_data[0] = [0] * 49  # 当日のデータをクリア
                            hist_date[0] = date_of_days_ago(cumul_date, 0)
                            hist_data[0][0] = hist_data[1][48]  # 前日（シフト後)24:00 → 当日00:00
                            hist_flag[hist_day - 1] = True
                            day_shift = 0
                            logger.info('[EXEC] Day-to-Day processed!')
                        hist_data[0][TIME_TB.index(cumul_time)] = cumul_wh  # 履歴データ → hist_data

                    # ページ再描画
                    draw_page[page]()
                    draw_cumul()

                # 瞬間電力値・瞬間電流値受信処理
                elif r_key == 'INST':
                    wattage_time = utime.time()
                    inst_data = r_data.decode().strip().split('/')
                    wattage = int(inst_data[0])
                    amperage = float(inst_data[1])
                    inst_mode = 'good'

                    draw_w_a()
                    logger.info('[INST] << %s', inst_data)

            utime.sleep(1)
            gc.collect()
            # print('[SYS_] mem_free = {} byte'.format(gc.mem_free()))

    except Exception as e:
        logger.error(e)
        machine.reset()
