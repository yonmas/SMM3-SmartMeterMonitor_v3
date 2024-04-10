from m5stack import lcd, speaker, btnA, btnB, btnC
from m5stack_ui import *
from machine import Timer, reset
import _thread
import binascii
import espnow
import gc
import logging
import math
import ntptime
import utime
import wifiCfg
from func_sub_core2 import beep, status
import func_sub_core2 as cnfg

# 定数初期値 : 優先順位　 　設定GSS > 設定ファイル > 初期値
config = {
    'WARNING_AMPERAGE': 30,   # 警告アンペア(A)
    'LCD_BRIGHTNESS_C2': 70,  # 画面の明るさ(0〜100)
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
rotation_timer = Timer(2)
indicator_timer = Timer(3)
checkWiFi_timer = Timer(4)

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


# 【exec】　WiFi接続チェック
def checkWiFi(arg):
    logger.info('[EXEC] Checking Wi-Fi.')
    if not wifiCfg.is_connected():
        logger.warning('[ERR.] Reconnect to WiFi')
        if not wifiCfg.reconnect():
            logger.warning('[SYS_] == system reset ==')
            reset()


# 【exec】　BEEP音鳴らしスレッド関数 ※うまくいかないため、機能を停止しています
def beep_sound():
    logger.info('[EXEC] Amperage alarm !')
    while True:
        if inst_mode != 'good':  # タイムアウトで表示ミュートされてるか、初期値のままならpass
            pass
        else:  # 警告閾値超えでBEEP ONなら
            if (amperage >= config['WARNING_AMPERAGE']) and (beep_on is True):
                # speaker.playTone(220, 2, volume=8) << 警告音鳴動
                utime.sleep(2)
        utime.sleep(0.1)


# 【exec】　擬似Boldタイプ文字表示
def print_b(text, x, y, col, w):
    for n in range(0, w):
        lcd.print(text, x + n, y, color=col)


# 【exec】　ページめくり処理スレッド関数
def flip_page(direction):
    logger.info('[EXEC] Flip page.')
    global page

    # ボタンが押されるたびにページを進める/戻す
    page = page + direction
    if page == len(draw_page):
        page = 0
    elif page == -1:
        page = len(draw_page) - 1

    # ボタンエリア以外は一旦画面全消し、ページ再描画
    lcd.rect(0, 0, 320, 224, BG_COLOR, BG_COLOR)
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
        logger.info('[EXEC] Auto_rotation On')
        auto_rotation_sw = True
    else:  # ストップ
        rotation_timer.deinit()
        logger.info('[EXEC] Auto_rotation Off')
        auto_rotation_sw = False

    draw_cumul()
    beep()


# 【exec】　画面初期化
def init_screen():
    screen = M5Screen()
    screen.set_screen_brightness(0)  # バックライトOFF
    lcd.setColor(bcolor=BG_COLOR)
    lcd.clear()
    lcd.rect(0, 224, 320, 240, 0x303030, 0x303030)
    draw_page[page]()
    draw_beep_icon(False)
    draw_cumul()
    if sum(hist_flag) == data_period + 1:
        lcd.circle(310, 232, 8, 0x1f77b4, 0x1f77b4)
    screen.set_screen_brightness(config['LCD_BRIGHTNESS_C2'])  # バックライト輝度設定


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
    lcd.print(created_date + ' ' + created_time, 2, 227, col)


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
    if monthly_e_energy == 0:
        monthly_e_energy_d = '-'
    else:
        monthly_e_energy_d = str(int(monthly_e_energy))
    lcd.font(lcd.FONT_DejaVu40)
    len_txt = lcd.textWidth(monthly_e_energy_d)
    lcd.print(monthly_e_energy_d, x + w - len_txt - 20, y + 5, color2)

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
        lcd.font(lcd.FONT_DejaVu72)
        lcd.print(str(wattage), 190 - lcd.textWidth(str(wattage)), 35, fc)
        lcd.font(lcd.FONT_DejaVu40)
        lcd.print('W', 190, 65, uncolor)
        # 瞬間電流表示
        lcd.font(lcd.FONT_DejaVu40)
        lcd.print(str(int(amperage)), 292 - lcd.textWidth(str(int(amperage))), 59, fc)
        lcd.font(lcd.FONT_DejaVu24)
        lcd.print('A', 293, 78, uncolor)

    # 電力量グラフ (当日と前日) 表示モード時
    elif draw_page[page] == draw_graph_1:
        lcd.rect(70, 0, 250, 63, BG_COLOR, BG_COLOR)
        # 瞬間電力値表示
        lcd.font(lcd.FONT_DejaVu56)
        lcd.print(str(wattage) + '     ', lcd.RIGHT, 13, fc)
        # W表示
        lcd.font(lcd.FONT_DejaVu24)
        lcd.print('W', 240, 36, uncolor)
        # 瞬間電流表示
        lcd.font(lcd.FONT_DejaVu24)
        lcd.print(str(int(amperage)), 300 - lcd.textWidth(str(int(amperage))), 37, fc)
        lcd.font(lcd.FONT_DejaVu18)
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

    lcd.font(lcd.FONT_Default)
    for i in range(0, 5):
        lcd.print('{:02}'.format(i * 6), i * 72 + 6, 208, tx_color1)
    print_b('{:.1f} kWh'.format(DAY_GRAPH_SCALE), 0, 48, tx_color1, 2)

    # グラフ描画メイン
    for n in range(0, 48):  # 毎30分 x 48
        # 前日のグラフ高さの計算
        if (hist_data[1][n + 1] == 0) or (hist_data[1][n] == 0):
            h_power_yesterday = 0
        else:
            h_power_yesterday = round((hist_data[1][n + 1] - hist_data[1][n]) * UNIT, 1)

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
            h_power_today = round((hist_data[0][n + 1] - hist_data[0][n]) * UNIT, 1)

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
            
    gc.collect()


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

    if created_time != '**:**':
        # データ集計セクション
        if TIME_TB.index(created_time) == 0:
            index = 48
        else:
            index = TIME_TB.index(created_time)

        if hist_data[0][0]:
            today_sub_t = round((hist_data[0][index] - hist_data[0][0]) * UNIT, 1)

        for n in range(1, draw_period + 1):
            if hist_data[n][0]:
                daily_sub_t[n] = round((hist_data[n][index] - hist_data[n][0]) * UNIT, 1)
                daily_cumul[n] = round((hist_data[n][48] - hist_data[n][0]) * UNIT, 1)

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
        lcd.font(lcd.FONT_Default)

        max_txt = str(GRAPH_SCALE) + ' kWh >'
        t_sub_t = '{:.1f} kWh'.format(today_sub_t)
        print_b(max_txt, 318 - lcd.textWidth(max_txt), 0 + 5, tx_color2, 2)
        print_b(' Today :', 5, 0 + 5, tx_color2, 2)
        print_b(t_sub_t, 145 - lcd.textWidth(t_sub_t), 0 + 5, tx_color2, 2)

        a_sub_t = '{:.1f}'.format(avg_sub_t)
        a_cumul = '{:.1f}'.format(avg_cumul)
        print_b(' AVG :', 19, 200 + 5, tx_color2, 2)
        print_b(a_sub_t, 107 - lcd.textWidth(a_sub_t), 200 + 5, tx_color2, 2)
        print_b(a_cumul, 153 - lcd.textWidth(a_cumul), 200 + 5, tx_color2, 2)

        # 7日間グラフの場合は日毎データ値を表示
        if draw_period == 7:
            for n in range(1, avg_period + 1):
                d_date = hist_date[n] + ' :'
                d_sub_t = '{:.1f}'.format(daily_sub_t[n])
                d_cumul = '{:.1f}'.format(daily_cumul[n])
                y = (n * 25) + 5
                lcd.print(d_date, 64 - lcd.textWidth(d_date), y, color=tx_color1)
                lcd.print(d_sub_t, 107 - lcd.textWidth(d_sub_t), y, color=tx_color1)
                lcd.print(d_cumul, 153 - lcd.textWidth(d_cumul), y, color=tx_color1)

        # 30日間グラフの場合は1週間ごとに日付を表示
        if draw_period == 30:
            for n in range(7, avg_period + 1, 7):
                d_date = hist_date[n] + ' :'
                y = (n // 7) * 44 + 8
                lcd.print(d_date, 64 - lcd.textWidth(d_date), y, color=tx_color1)

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
    lcd.font(lcd.FONT_Default)

    print_b('AM:', 0, 0, col_caption, 2)
    print_b('Tdy:', 68 - lcd.textWidth('Tdy:'), 0, col_caption, 2)
    print_b(caption + ':', 97 - int(lcd.textWidth(caption + ':')/2), 0, col_caption, 2)
    print_b('Diff', 149 - lcd.textWidth('Diff'), 0, col_caption, 2)
    print_b('PM:', 166, 0, col_caption, 2)
    print_b('Tdy:', 234 - lcd.textWidth('Tdy:'), 0, col_caption, 2)
    print_b(caption + ':', 263 - int(lcd.textWidth(caption + ':')/2), 0, col_caption, 2)
    print_b('Diff', 315 - lcd.textWidth('Diff'), 0, col_caption, 2)
    lcd.print('|', 155, 0, color=tx_color1)

    # データ集計セクション
    for n in range(0, 12):  # 0〜11
        nn = n * 2  # 元データが30分毎なのでステップを倍に
        for i in range(0, calc_period + 1):     # i=0 当日, i=n n日前
            if (hist_data[i][nn + 2] == 0) or (hist_data[i][nn] == 0):
                hour_power[i][n] = 0
            else:  # 1時間あたりの定時積算電力量（単位：kWh）
                hour_power[i][n] = round((hist_data[i][nn + 2] - hist_data[i][nn]) * UNIT, 1)

            if ((hist_data[i][nn + 24 + 2] == 0) or (hist_data[i][nn + 24] == 0)):
                hour_power[i][n + 12] = 0
            else:  # 1時間あたりの定時積算電力量（単位：kWh）
                hour_power[i][n + 12] = round((hist_data[i][nn + 24 + 2]
                                               - hist_data[i][nn + 24]) * UNIT, 1)

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
            diff_PM_str = '{:3.1f}'.format(diff_PM)

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
        AM_str = '{:02}:'.format(n)
        PM_str = '{:02}:'.format(n+12)
        power_AM_str = '{:3.1f}:'.format(hour_power[0][n])
        power_PM_str = '{:3.1f}:'.format(hour_power[0][n+12])
        avg_AM_str = '{:3.1f}:'.format(avg_hour_power[n])
        avg_PM_str = '{:3.1f}:'.format(avg_hour_power[n+12])
        
        y = (n + 1) * 16
        lcd.print(AM_str, 2, y, color=0xd0d000)
        lcd.print(power_AM_str, 68 - lcd.textWidth(power_AM_str), y, color=tx_color1)
        lcd.print(avg_AM_str, 110 - lcd.textWidth(avg_AM_str), y, color=tx_color1)
        lcd.print(diff_AM_str, 149 - lcd.textWidth(diff_AM_str), y, color=color_diff_AM)
        lcd.print('|', 155, y, color=tx_color1)
        lcd.print(PM_str, 168, y, color=0xd0d000)
        lcd.print(power_PM_str, 234 - lcd.textWidth(power_PM_str), y, color=tx_color1)
        lcd.print(avg_PM_str, 276 - lcd.textWidth(avg_PM_str), y, color=tx_color1)
        lcd.print(diff_PM_str, 315 - lcd.textWidth(diff_PM_str), y, color=color_diff_PM)
        
    # 当日(現時刻まで)および期間平均の24時間積算電力量と、比(%)を最下段に表示
    if created_time != '**:**':
        if TIME_TB.index(created_time) == 0:
            index = 24
        else:
            index = int(TIME_TB.index(created_time) / 2)

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

        lcd.font(lcd.FONT_Default)
        lcd.print(hist_data_of_Today, 69, 211, color=0xffffff)
        lcd.print(hist_data_of_avg, 195, 211, color=0xffffff)
        lcd.print(hist_data_Ratio, 276, 211, color=color_ratio)

    del hour_power, avg_hour_power
    gc.collect()


# 【config】　設定用GSSから設定をリロード
def reload_config(config):
    global DAY_GRAPH_SCALE, GRAPH_SCALE, BG_COLOR, UNIT

    lcd.clear()
    lcd.font(lcd.FONT_DejaVu18)
    lcd.println('Config_GSS reloading.', 0, 0, color=0xFFFFFF)

    config = cnfg.update_config_from_gss(api_config, config)
    cnfg.save_config(config)
    DAY_GRAPH_SCALE, GRAPH_SCALE, BG_COLOR, UNIT = cnfg.set_config(config)

    log_level = getattr(logging, config['LOG_LEVEL'], None)
    logging.basicConfig(level=log_level)
    logger.info('[INIT] Logging level = %s', config['LOG_LEVEL'])

    init_screen()
    beep()


# 【exec】　積算電力-履歴データ取得
def get_hist_data():
    global hist_day, hist_flag, hist_date, hist_data, req_flag
    # global UNIT

    logger.info('[INIT] Get Historical DATA')

    hist_day = 0
    hist_flag = [False] * (data_period + 1)
    hist_date = ['**/**'] * (data_period + 1)
    hist_data = [[0 for i in range(49)] for j in range(data_period + 1)]
    req_flag = [False] * (data_period + 2)

    # UNIT = None  # << UNIT を取得する場合

    init_screen()
    indicator_timer.deinit()
    indicator_timer.init(period=100, mode=indicator_timer.PERIODIC, callback=draw_indicator)
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

        # Start checking the WiFi connection
        checkWiFi_timer.init(period=60 * 1000, mode=checkWiFi_timer.PERIODIC, callback=checkWiFi)

        utime.sleep(0.1)
        lcd.clear(0x000000)
        utime.sleep(0.1)
        lcd.font(lcd.FONT_DejaVu18)
        lcd.println('Welcome to SMM3 !', 0, 0, color=0xFF0000)

        # 定数の読み込み（ファイル、Googleスプレッドシート）
        config = cnfg.update_config_from_file(config)
        api_config = cnfg.get_api_config()
        config = cnfg.update_config_from_gss(api_config, config)
        cnfg.save_config(config)
        DAY_GRAPH_SCALE, GRAPH_SCALE, BG_COLOR, UNIT = cnfg.set_config(config)

        log_level = getattr(logging, config['LOG_LEVEL'], None)
        logging.basicConfig(level=log_level)
        logger.info('[INIT] Logging level = %s', config['LOG_LEVEL'])

        # RTC設定（時刻設定）
        ntp = ntptime.client(host='jp.pool.ntp.org', timezone=9)
        status('Set Time.')

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

        # BEEP音鳴らしスレッド起動
        _thread.start_new_thread(beep_sound, ())
        status('BEEP thread start.')

        status('== Start monitoring ==')
        utime.sleep(3)

        # データ取得処理
        hist_day = 0
        hist_flag = [False] * (data_period + 1)
        hist_date = ['**/**'] * (data_period + 1)
        hist_data = [[0 for i in range(49)] for j in range(data_period + 1)]
        req_flag = [False] * (data_period + 2)

        # UNITをメーターからの取得値によらず固定としている (UNIT)
        UNIT = config['UNIT']

        # 表示値初期値
        wattage = 0
        amperage = 0
        e_energy = 0
        monthly_e_energy = 0
        charge = 0
        collect = '****-**-** **:**:**'
        created = '****-**-** **:**:**'
        created_date = '****-**-**'
        created_time = '**:**'

        # タイマー初期化
        wattage_time = utime.time()
        req_time = utime.time() - 120

        # 画面初期化
        init_screen()
        indicator_timer.deinit()
        indicator_timer.init(period=100, mode=indicator_timer.PERIODIC, callback=draw_indicator)


        # メインループ
        while True:

            # 瞬間電力値の更新が[TIMEOUT_SUB]秒以上途絶えたら、電力値<薄黄色>表示　
            if utime.time() - wattage_time >= config['TIMEOUT_SUB']:
                if inst_mode == 'good':
                    inst_mode = 'lost'
                    draw_w_a()

            # # 'UNIT' 積算電力量-[単位x係数]をリクエスト  << UNIT を取得する場合
            # if UNIT is None:
            #     espnow.broadcast(data='UNIT')
            #     logger.info('[UNIT] -> Request UNIT')

            # 'REQ' 積算電力量-履歴データをリクエスト
            if hist_day == 0:
                init_time = utime.time()
            if req_flag[hist_day] is False and hist_day <= data_period:
                espnow.broadcast(data='REQ' + '{:02}'.format(hist_day))
                req_flag[hist_day] = True
                req_time = utime.time()
                logger.debug('[SENT] -> Key = [REQ%2d]', hist_day)
            elif utime.time() - req_time > 30:  # 指定秒数、リプライがなけらば再リクエスト
                req_flag[hist_day] = False

            # # 'UNIT' 積算電力量-[単位x係数]をリクエスト
            # if UNIT is None:
            #     if request_UNIT is False:
            #         espnow.broadcast(data='UNIT')
            #         logger.info('[UNIT] -> Request UNIT')
            #         request_UNIT = True

            # 【RCEV】 親機からデータを受信(ESP NOW)
            d = espnow.recv_data()
            if (len(d[2]) > 0):
                header = str(d[2][:2].decode().strip())  # 先頭2文字が header
                if header == 'M:':  # 親機からのデータ 'M:〜' のみ処理
                    r_key = str(d[2][2:6].decode().strip())  # 2-5文字が key
                    r_data = d[2][6:].strip()  # 6文字以降がデータ
                    logger.info('[RECV] <- Key = [%s]', r_key)

                    # 【BOOT】 親機起動時処理 : 履歴データ再取得
                    if r_key == 'BOOT':
                        get_hist_data()

                    # 【TOUT】 親機〜スマートメーター間タイムアウト通知受信処理
                    elif r_key == 'TOUT':
                        if inst_mode != 'timeout':
                            inst_mode = 'timeout'
                            draw_w_a()

                    # # 【UNIT】 積算電力量-[単位x係数]受信処理  << UNIT を取得する場合
                    # elif r_key == 'UNT=':
                    #     UNIT = float(r_data.decode())
                    #     logger.info('[UNIT] <- UNIT = %s', UNIT)
                    #     request_UNIT = False

                    # 【HIST】 積算電力量-履歴データ受信処理
                    elif r_key[:2] == 'ID':
                        id = int(r_key[2:4].strip())
                        d1 = r_data[:24].decode('utf-8').strip()
                        _created_date = d1[:10]
                        _created_time = d1[11:16]
                        _hist_date = d1[19:24]
                        _data = binascii.hexlify(r_data[24:]).decode('utf-8').strip()

                        if (id == 0) and created_time == '':
                            cumul_date = _created_date
                            cumul_time = _created_time

                        if (id == hist_day):  # and UNIT:  # 受信データ = 要求日のデータ なら
                            if hist_flag[id] is False:  # 要求日のデータが存在しなければ、受信処理
                                for k in range(0, 49):
                                    if int(_data[(k * 8):(k * 8) + 8], 16) > 0x05f5e0ff:
                                        hist_data[id][k] = 0  # 0x05f5e0ff(99999999) 超えなら 0
                                    else:
                                        hist_data[id][k] = int(_data[(k * 8):(k * 8) + 8], 16)
                                hist_date[id] = _hist_date
                                hist_flag[id] = True

                                logger.info('[HIST] <- [(%d) %s %s [%s %.1f - %.1f : %.1f]]',
                                            id, _created_date, _created_time,
                                            hist_date[id],
                                            hist_data[id][0] * UNIT,
                                            hist_data[id][47] * UNIT,
                                            hist_data[id][48] * UNIT)
                                logger.debug('[HIST] <- Raw = %s', hist_data[id])

                                draw_page[page]()  # ページ再描画
                                draw_cumul()

                                if sum(hist_flag) == data_period + 1:
                                    indicator_timer.deinit()
                                    beep()
                                    t = utime.time() - init_time
                                    logger.info('[HIST] Data acquisition completed. time = %d', t)
                                    lcd.circle(310, 232, 8, 0x1f77b4, 0x1f77b4)

                            hist_day += 1

                    # 【INST】 瞬間電力値・瞬間電流値受信処理
                    elif r_key == 'INST':
                        wattage_time = utime.time()
                        inst_data = r_data.decode().strip().split('/')
                        wattage = int(inst_data[0])
                        amperage = float(inst_data[1])
                        inst_mode = 'good'

                        draw_w_a()
                        logger.info('[INST] <- %s', inst_data)

                    # 【CUML】 積算電力量受信処理
                    elif r_key == 'CUML':
                        cumul_data = r_data.decode().strip().split('/')
                        collect = cumul_data[0]  # 直近の検針日時
                        created = cumul_data[1]
                        created_date = created.strip().split(' ')[0]  # 定時積算電力取得日
                        created_time = created.strip().split(' ')[1][:5]  # 定時積算電力取得時刻
                        e_energy = round(float(cumul_data[2]), 1)  # 積算電力量
                        monthly_e_energy = round(float(cumul_data[3]), 1)  # 今月の電力量(created_dateまで)
                        charge = cumul_data[4]  # 今月の電気料金(created_dateまで)

                        logger.info('[CUML] <- %s', cumul_data)

                        # 日跨ぎ処理
                        if TIME_TB.index(created_time) == 0:
                            hist_data[0][48] = int(e_energy / UNIT)  # 00:00のデータなら、当日24:00のデータに
                        else:
                            # 00:30のデータ かつ 当日01:00のデータがある（日跨ぎ処理未実施）なら、日跨ぎ処理を行う
                            if (TIME_TB.index(created_time) == 1) and (hist_data[0][2] != 0):
                                for id in range(data_period, 0, -1):
                                    hist_data[id] = hist_data[id - 1]  # 履歴データシフト
                                    hist_date[id] = hist_date[id - 1]  # 履歴日付けシフト
                                hist_data[0] = [0] * 49  # 当日のデータをクリア
                                hist_date[0] = date_of_days_ago(created_date, 0)
                                hist_data[0][0] = hist_data[1][48]  # 前日（シフト後)24:00 → 当日00:00
                                if hist_day <= data_period:
                                    hist_flag[hist_day] = True
                                if hist_day < data_period:
                                    hist_day += 1
                                logger.info('[EXEC] Day-to-Day processed!')
                                ntp = ntptime.client(host='jp.pool.ntp.org', timezone=9)  # 時計合わせ
                            # 履歴データ → hist_data
                            hist_data[0][TIME_TB.index(created_time)] = int(e_energy / UNIT)

                        # ページ再描画
                        draw_page[page]()
                        draw_cumul()

            gc.collect()
            # utime.sleep(0.5)
            # print('[SYS_] mem_free_end = {} byte'.format(gc.mem_free()))

    except Exception as e:
        logger.error('[ERR.] == Final Exception ==: %s', e)

    finally:
        logger.critical('[SYS_] == system reset ==')
        reset()
