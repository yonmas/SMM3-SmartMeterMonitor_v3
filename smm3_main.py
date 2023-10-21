from m5stack import lcd, btnA, btnB
from machine import Timer, reset
import binascii
import espnow
import gc
import logging
import math
import ntptime
import sys
import utime
import wifiCfg
from bp35a1 import BP35A1
from calc_charge import CalcCharge
from func_main import beep, status
import func_main as cnfg

# 定数初期値
config = {
    'B_ID': None,
    'B_PASSWORD': None,
    'A_ID': '*',
    'A_KEY': '*',
    'A_INTERVAL': 30,
    'CONTRACT_AMPERAGE': 40,
    'WARNING_AMPERAGE': 30,
    'COLLECT_MONTH': [12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    'COLLECT_CALENDAR': [''] * 13,
    'COLLECT_DATE': 15,
    'CHARGE_FUNC': 'tepco',
    'BASE': 1180.96,
    'RATE1': 30.0,
    'RATE2': 36.6,
    'RATE3': 40.69,
    'SAIENE': 0,
    'NENCHO': 0,
    'TIMEOUT_MAIN': 30,
    'LOG_LEVEL': 'INFO',  # 'CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'
}

# Global variables #
logger = None               # Logger object
logger_name = 'MAIN'        # Logger name
bp35a1 = None               # BPA35A1 object
ambient_client = None       # Ambient instance
ipv6_addr = None
coefficient = None
unit = None
orient = lcd.LANDSCAPE      # Display orientation
max_retries = 30            # Maximum number of times to retry
data_mute = False
ampere_limit_over = False
step = 0

# タイマー
indicator_timer = Timer(-1)
checkWiFi_timer = Timer(-1)

# 履歴データを取得する期間（日）
data_period = 35            # 何日前までのデータを参照するか

# Colormap (tab10)
colormap = (
    0x1f77b4,  # tab:blue
    0xff7f0e,  # tab:orange
    0x2ca02c,  # tab:green
    0xd62728,  # tab:red
    0x9467bd,  # tab:purple
    0x8c564b,  # tab:brown
    0xe377c2,  # tab:pink
    0x7f7f7f,  # tab:gray
    0xbcbd22,  # tab:olive
    0x17becf,  # tab:cyan
)

bgcolor = 0x000000    # Background color
uncolor = 0xa0a0a0    # Unit color
color1 = colormap[0]  # Current value color
color2 = 0xe08040     # Total value color
color3 = colormap[3]  # Limit over color
grayout = 0x303030

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


# 【exec】　スクリーン上下反転
def flip_lcd_orientation():
    global orient

    if orient == lcd.LANDSCAPE:
        orient = lcd.LANDSCAPE_FLIP
    else:
        orient = lcd.LANDSCAPE

    lcd.orient(orient)
    draw_main()
    beep()


# 【exec】　WiFi接続チェック
def checkWiFi(arg):
    if not wifiCfg.is_connected():
        logger.warning('[ERR.] Reconnect to WiFi')
        if not wifiCfg.reconnect():
            logger.warning('[SYS_] == system reset ==')
            reset()


# 【exec】　プログレスバーの表示
def progress(percent):
    (w, h) = lcd.screensize()
    x = (w - 6) * percent // 100
    lcd.rect(3, h - 12, x, 12, bgcolor, color1)
    lcd.rect(3 + x, h - 12, w - 6, 12, bgcolor, bgcolor)
    lcd.font(lcd.FONT_DefaultSmall, transparent=True)
    lcd.text(lcd.CENTER, h - 10, '{}%'.format(percent), uncolor)


# 【draw】　メイン画面表示
def draw_main():
    draw_wattage(wattage)
    draw_amperage(amperage)
    draw_collect_range(collect, created)
    draw_monthly_e_energy(monthly_e_energy)
    draw_monthly_charge(charge)


# 【draw】　データ受信インジケーター描画
def draw_indicator(timer):
    global step
    rad = 2 * math.pi * (step / 15)
    vol = (1 - math.cos(rad)) / 2 * 0xff
    col = int('0x' + '{:x}'.format(round(vol * 1)) + '0000', 16)
    lcd.circle(234, 7, 3, col, col)
    step += 1


# 【draw】　瞬時電力計測値の表示
def draw_wattage(wattage):
    if ampere_limit_over:
        fc = color3
    else:
        if data_mute:
            fc = grayout
        else:
            fc = color1

    (x, y, w, h) = (116, 3, 124, 47)
    lcd.rect(x, y, w, h, bgcolor, bgcolor)

    if wattage == 0:
        wattage = '- '
    else:
        wattage = str(int(wattage))
    lcd.font(lcd.FONT_DejaVu40)
    lcd.print(wattage, x + w - 20 - lcd.textWidth(wattage), y + 5, fc)
    lcd.font(lcd.FONT_DejaVu18)
    lcd.print('W', lcd.LASTX, y + (h - 18), uncolor)


# 【draw】　瞬時電流計測値の表示
def draw_amperage(amperage):
    if ampere_limit_over:
        fc = color3
    else:
        if data_mute:
            fc = grayout
        else:
            fc = color1

    (x, y, w, h) = (3, 3, 113, 47)
    lcd.rect(x, y, w, h, bgcolor, bgcolor)

    if amperage == 0:
        amperage = '- '
    else:
        amperage = str(int(amperage))
    lcd.font(lcd.FONT_DejaVu40)
    lcd.print(amperage, x + 51 - lcd.textWidth(amperage), y + 5, fc)
    lcd.font(lcd.FONT_DejaVu18)
    lcd.print('A', lcd.LASTX, y + (h - 18), uncolor)

    CONTRACT_AMPERAGE = str(int(config['CONTRACT_AMPERAGE']))
    lcd.font(lcd.FONT_DejaVu24)
    lcd.print(CONTRACT_AMPERAGE, x + 65, y + (h - 24), uncolor)
    lcd.font(lcd.FONT_DejaVu18)
    lcd.print('A', lcd.LASTX, y + (h - 18), uncolor)


# 【draw】　今月（検針日を起点）の日付範囲を表示
def draw_collect_range(collect, created):
    (x, y, w, h) = (3, 50, 237, 25)
    lcd.rect(x, y, w, h, bgcolor, bgcolor)

    s = '{}~{}'.format(collect[5:10], created[5:10])
    lcd.font(lcd.FONT_DejaVu18)
    lcd.print(s, int(x + (w - lcd.textWidth(s)) / 2), y + 5, uncolor)


# 【draw】　今月（検針日を起点）の電力量の表示
def draw_monthly_e_energy(monthly_e_energy):
    (x, y, w, h) = (3, 75, 107, 60)
    lcd.rect(x, y, w, h, bgcolor, bgcolor)

    if monthly_e_energy == 0:
        monthly_e_energy = '- '
    else:
        monthly_e_energy = str(int(monthly_e_energy))
    lcd.font(lcd.FONT_DejaVu40)
    lcd.print(monthly_e_energy, x + w - lcd.textWidth(monthly_e_energy) - 15, y + 5, color2)
    lcd.font(lcd.FONT_DejaVu18)
    lcd.print('kWh', x + w - lcd.textWidth('kWh') - 15, y + 40, uncolor)


# 【draw】　今月（検針日を起点）の電気料金の表示
def draw_monthly_charge(charge):
    (x, y, w, h) = (110, 75, 130, 60)
    lcd.rect(x, y, w, h, bgcolor, bgcolor)

    if charge == 0:
        charge = '- '
    else:
        charge = str(int(charge))
    lcd.font(lcd.FONT_DejaVu40)
    lcd.print(charge, x + w - lcd.textWidth(charge), y + 5, color2)
    lcd.font(lcd.FONT_DejaVu18)
    lcd.print('Yen', x + w - lcd.textWidth('Yen'), y + 40, uncolor)


# 【draw】　TIMEOUT_MAIN秒以上、スマートメーターからのデータが途切れた場合は文字色をグレー表示
def check_timeout(inst_time):
    global data_mute
    if ((utime.time() - inst_time) >= TIMEOUT_MAIN) and (data_mute is False):
        data_mute = True
        draw_wattage(wattage)
        draw_amperage(amperage)
        espnow.broadcast(data=str('M:TOUT'))  # ESP NOW で timeout を子機に通知


# 【config】　インスタンスの設定
def set_instance(config):
    global bp35a1, ambient_client, logger, calc_charge_func

    status('Create objects', uncolor)
    bp35a1 = BP35A1(config['B_ID'],
                    config['B_PASSWORD'],
                    config['COLLECT_CALENDAR'],
                    ipv6_addr,
                    coefficient,
                    unit,
                    progress_func=progress,
                    log_level=config['LOG_LEVEL'])
    logger.info('[INIT] BP35A1 config: (%s, %s, %s)', config['B_ID'],
                config['B_PASSWORD'], config['COLLECT_CALENDAR'])

    # Ambient のアカウント設定
    if (config['A_ID'] != '*') and (config['A_KEY'] != '*'):
        import ambient
        ambient_client = ambient.Ambient(config['A_ID'], config['A_KEY'])
        logger.info('[INIT] Ambient config: (%s, %s)',
                    config['A_ID'], config['A_KEY'])

    calc_instance = CalcCharge(
        config['BASE'],    # 基本料金
        config['RATE1'],   # 1段料金
        config['RATE2'],   # 2段料金
        config['RATE3'],   # 3段料金
        config['SAIENE'],  # 再エネ発電賦課金単価
        config['NENCHO']   # 燃料費調整単価
    )

    try:
        calc_charge_func = getattr(calc_instance, config['CHARGE_FUNC'])
    except Exception as e:
        status('No calc_charge_method !', 0xff0000)
        logger.error(e)
        beep()
        utime.sleep(30)
        sys.exit()

    logger.info('[INIT] Charge Function: %s', calc_charge_func.__name__)

    log_level = getattr(logging, config['LOG_LEVEL'], None)
    logging.basicConfig(level=log_level)
    logger.info('[INIT] Logging level = %s', config['LOG_LEVEL'])


# 【config】　設定用GSSから設定をリロード
def reload_config(config):
    global TIMEOUT_MAIN, WARNING_AMPERAGE, CONTRACT_AMPERAGE
    # global inst_time, cumul_time, cumul_flag

    lcd.clear()
    status('Reloading config from GSS.', uncolor)

    config = cnfg.update_config_from_gss(api_config, config)
    cnfg.save_config(config)
    config, TIMEOUT_MAIN, WARNING_AMPERAGE, CONTRACT_AMPERAGE = cnfg.set_config(config)
    set_instance(config)
    draw_main()
    beep()

    # inst_time = utime.time() - 120  # INST タイマー
    # cumul_time = utime.time() - 120  # CUML タイマー
    # cumul_flag = False


# 【send】 'UNIT' 積算電力量-[単位x係数]のリクエストに応答
def send_unit(unit_flag, unit_count):
    if unit_flag is False:
        espnow.broadcast(data=str('M:UNT=' + str(UNIT)))
        unit_flag = True
        logger.info('[UNIT] -> %.1f', UNIT)
    else:
        unit_count += 1
        logger.debug('[UNIT] Skip UNIT Request: counter = %d', unit_count)
        if unit_count >= 10:  # 最大リトライ回数
            unit_count = 0
            unit_flag = False
            logger.debug('[UNIT] Reset UNIT Counter')

    return unit_flag, unit_count


# 【send】 積算電力量　取得 ＆ 表示 & 子機送信
def send_cumul():
    logger.debug('[CUML] == Monthly e-Energy & Monthly Charge ==')

    result = False
    _collect = collect
    _created = created
    _e_energy = e_energy
    _monthly_e_energy = monthly_e_energy
    _charge = charge

    try:
        # 取得
        _created, _e_energy = bp35a1.get_cumul_e_energy()
        _collect, _days_ago = bp35a1.get_collect_date()
        if hist_flag[_days_ago] is True:
            _e_energy_0 = hist_data[_days_ago][0] * UNIT
        else:
            _e_energy_0 = bp35a1.get_collected_e_energy()
        _monthly_e_energy = _e_energy - _e_energy_0
        _charge = calc_charge_func(config['CONTRACT_AMPERAGE'], _monthly_e_energy)

        # 子機送信
        CUML = str('M:CUML' + str(_collect) + '/' + str(_created) + '/' + str(_e_energy) + '/'
                   + str(_monthly_e_energy) + '/' + str(_charge))
        espnow.broadcast(data=CUML)
        logger.info('[CUML] -> [%s]', str(CUML))

        result = True

    except Exception as e:
        logger.error('[CUML] %s', e)

    return _collect, _created, _e_energy, _monthly_e_energy, _charge, result


# 【send】 瞬時電力・瞬時電流　取得 ＆ 表示 ＆ 子機送信
def send_inst():
    logger.debug('[INST] == Wattage & Amperage ==')

    result = False
    _wattage = wattage
    _amperage = amperage

    try:
        # 取得
        (_wattage, _amperage) = bp35a1.get_instantaneous_data()

        # 子機送信：瞬時電力、瞬時電力発信
        if isinstance(_wattage, int) and isinstance(_amperage, float):
            espnow.broadcast(data=str('M:INST' + str(_wattage) + '/' + str(_amperage)))
            logger.info('[INST] -> [%s , %s]', str(_wattage), str(_amperage))
            result = True

        else:
            raise Exception('Illeagal data: [' + _wattage + ']-[' + _amperage + ']')

    except Exception as e:
        logger.error('[INST] %s', e)

    return _wattage, _amperage, result


# 【send】 Ambientデータ送信：Send every 30 seconds
def send_ambient():

    result = False

    try:
        if ambient_client:
            a_result = ambient_client.send({'d1': amperage,
                                            'd2': wattage,
                                            'd3': monthly_e_energy,
                                            'd4': charge})

            result = True

            if a_result.status_code != 200:
                raise Exception('ambient.send() failed. status: ', a_result.status_code)

    except Exception as e:
        logger.error('[AMBIENT] %s', e)

    return result


# 【exec】　積算電力-履歴データ取得
def get_hist_data():
    global hist_day, hist_flag, hist_created, hist_date, hist_data, day_shift, cumul_flag
    global hist_time, cumul_time
    
    logger.info('[INIT] Get Historical DATA')

    hist_day = 0  # データ取得日
    hist_flag = [False] * (data_period + 1)  # 履歴データがあるかどうか
    hist_created = [''] * (data_period + 1)  # 履歴データの生成日
    hist_date = [''] * (data_period + 1)  # 履歴データの日にち
    hist_data = [[0 for i in range(49)] for j in range(data_period + 1)]
    hist_time = [utime.time() - 1200] * (data_period + 1)  # HIST タイマー
    day_shift = 0  # 0:00〜0:30 の間はシフト（検討）

    cumul_flag = False
    cumul_time = utime.time() - 1200  # CUML タイマー

    indicator_timer.deinit()
    indicator_timer.init(period=200, mode=indicator_timer.PERIODIC, callback=draw_indicator)

    # 親機起動を通知
    espnow.broadcast(data='M:BOOT')
    utime.sleep(0.1)

    beep()

# 【exec】 取得済みの積算電力-履歴データを子機に続けて送信
def send_all_hist_data(id):
    logger.info('[INIT] Continuously send all hist. data.')
    _hist_time = [utime.time() - 1200] * (data_period + 1)  # HIST タイマー
    _time = utime.time()
    recv = True  # データ受信フラグ
    while utime.time() - _time < 30:  # 子機からのリクエストが30秒以上途絶えたら終了

        # 指定秒数以内の重複リクエストはスキップ
        if recv and hist_flag[id] is True and utime.time() - _hist_time[id] > 30:
            _send_data = ''
            for k in range(0, 49):
                _send_data += '{:08X}'.format(hist_data[id][k])
            send_data = (bytes('M:ID{:02}{}{:5}'
                               .format(id, hist_created[id], hist_date[id]), 'UTF-8')
                         + binascii.unhexlify(_send_data + '00'))
            espnow.broadcast(data=send_data)
            _hist_time[id] = utime.time()
            _time = utime.time()

            logger.info('[HIST] -> [(%d) %s [%s %.1f - %.1f : %.1f]]',
                        id, hist_created[id],
                        hist_date[id],
                        hist_data[id][0] * UNIT,
                        hist_data[id][47] * UNIT,
                        hist_data[id][48] * UNIT)
            logger.debug('[HIST] -> Raw = %s', hist_data[id])
            # logger.debug('[HIST] -> [%d, %s]', id, binascii.hexlify(send_data).decode('utf-8'))
            if id == 30:
                return id, _hist_time

        recv = False
        while not recv and utime.time() - _time < 30:  # 子機からのリクエストが30秒以上途絶えたら終了
            d = espnow.recv_data()
            if (len(d[2]) > 0):
                key = str(d[2].decode().strip())
                logger.info('[RECV] <- Key = [%s]', key)
                if key.startswith('REQ'):
                    id = int(key[3:5])
                    recv = True  # データ受信フラグ

    return id, _hist_time


if __name__ == '__main__':

    try:
        # logger 初期化
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(logger_name)

        # WiFi　&ESP-NOW 設定
        lcd.orient(lcd.PORTRAIT_FLIP)
        wifiCfg.autoConnect(lcdShow=True)
        wifiCfg.wlan_ap.active(True)
        espnow.init(0)

        # Start checking the WiFi connection
        checkWiFi_timer.init(period=60 * 1000, mode=checkWiFi_timer.PERIODIC, callback=checkWiFi)

        lcd.clear()
        lcd.orient(orient)
        status('Welcome to SMM3 !', uncolor)

        # 定数の読み込み（ファイル、Googleスプレッドシート）
        config = cnfg.update_config_from_file(config)
        api_config = cnfg.get_api_config()
        config = cnfg.update_config_from_gss(api_config, config)
        cnfg.save_config(config)
        config, TIMEOUT_MAIN, WARNING_AMPERAGE, CONTRACT_AMPERAGE = cnfg.set_config(config)
        set_instance(config)

        # RTC設定（時刻設定）
        ntp = ntptime.client(host='jp.pool.ntp.org', timezone=9)
        status('Set Time.', uncolor)

        # ボタン検出スレッド起動
        # Aボタン       スクリーン上下反転
        # Aボタン長押し  GSS から config リロード
        # Bボタン長押し  履歴データ再取得

        btnA.wasReleased(flip_lcd_orientation)
        btnA.pressFor(0.8, lambda config=config: reload_config(config))
        btnB.pressFor(0.8, get_hist_data)
        status('Button thread start.', uncolor)

        # Connecting to Smart Meter
        status('Connecting SmartMeter', uncolor)
        (channel, pan_id, mac_addr, lqi, ipv6_addr, coefficient, unit) = bp35a1.open()
        logger.info('[INIT] Connected. BP35A1: (%s, %s, %s, %s, %s)',
                    channel, pan_id, mac_addr, lqi, ipv6_addr)

        # 親機起動を通知
        espnow.broadcast(data='M:BOOT')
        utime.sleep(0.1)
        # espnow.broadcast(data=str('M:UNT=' + str(UNIT)))

        status('== Start monitoring ==', uncolor)
        utime.sleep(1)

        # データ取得処理
        hist_day = 0  # データ取得日
        hist_flag = [False] * (data_period + 1)  # 履歴データがあるかどうか
        hist_created = [''] * (data_period + 1)  # 履歴データの生成日
        hist_date = [''] * (data_period + 1)  # 履歴データの日にち
        hist_data = [[0 for i in range(49)] for j in range(data_period + 1)]
        day_shift = 0  # 0:00〜0:30 の間はシフト（検討）
        cumul_flag = False

        UNIT = unit * coefficient
        
        # << UNIT を子機に送信する場合
        unit_flag = True  # << UNIT を子機に送信する場合はコメントアウト
        unit_count = 0

        # 表示値初期値
        wattage = 0
        amperage = 0
        e_energy = 0
        monthly_e_energy = 0
        charge = 0
        collect = '****-**-** **:**:**'
        created = '****-**-** **:**:**'

        # タイマー初期化
        hist_time = [utime.time() - 1200] * (data_period + 1)  # HIST タイマー
        cumul_time = utime.time() - 1200  # CUML タイマー
        inst_time = utime.time() - 1200  # INST タイマー
        ambient_time = utime.time() - 1200  # Ambient タイマー
        ping_time = utime.time() - 1200  # ping タイマー
        
        # 画面初期化
        lcd.clear()
        draw_main()
        indicator_timer.deinit()
        indicator_timer.init(period=200, mode=indicator_timer.PERIODIC, callback=draw_indicator)

        retries = 0  # リトライカウンターリセット


        # メインループ
        while retries < max_retries:

            # 【INST】 瞬時電力・瞬時電流　取得 ＆ 表示 ＆ 子機送信：Updated every 10 seconds
            if (utime.time() - inst_time) >= 10:
                wattage, amperage, result = send_inst()
                inst_time = utime.time()
                if result is True:
                    retries = 0
                    data_mute = False  # 表示ミュート解除

                    # アンペア警告域チェック
                    if amperage >= WARNING_AMPERAGE:
                        ampere_limit_over = True
                    else:
                        ampere_limit_over = False

                    # 表示
                    draw_wattage(wattage)
                    draw_amperage(amperage)

                else:
                    retries += 1

            check_timeout(inst_time)  # スマートメーターからのデータのタイムアウト判定

            # 【CUML】 積算電力量　取得 ＆ 表示 & 子機送信：Updated every 10 minutes
            if ((((utime.localtime()[4] - 1) % 10 == 0) and (utime.time() - cumul_time >= 60))
                or ((cumul_flag is False) and (utime.time() - cumul_time >= 60))):
                utime.sleep(1)
                cumul_flag = False
                collect, created, e_energy, monthly_e_energy, charge, result = send_cumul()
                cumul_time = utime.time()
                if result is True:
                    created_date = created[:10]
                    created_time = created[11:16] 
                    retries = 0
                    cumul_flag = True
                    
                    # 日跨ぎ処理
                    if TIME_TB.index(created_time) == 0:
                        hist_data[0][48] = int(e_energy / UNIT)  # 00:00のデータなら、当日24:00のデータに
                    else:
                        # 00:30のデータ かつ 当日01:00のデータがある（日跨ぎ処理未実施）なら、日跨ぎ処理を行う
                        if TIME_TB.index(created_time) == 1 and hist_data[0][2] != 0:
                            for id in range(data_period, 0, -1):
                                hist_created[id] = hist_created[id - 1]
                                hist_date[id] = hist_date[id - 1]  # 履歴日付けシフト
                                hist_data[id] = hist_data[id - 1]  # 履歴データシフト
                            hist_data[0] = [0] * 49  # 当日のデータをクリア
                            hist_date[0] = date_of_days_ago(created_date, 0)
                            hist_data[0][0] = hist_data[1][48]  # 前日（シフト後)24:00 → 当日00:00
                            hist_flag[hist_day] = True
                            day_shift = 0
                            logger.info('[EXEC] Day-to-Day processed!')
                            ntp = ntptime.client(host='jp.pool.ntp.org', timezone=9)  # 時計合わせ
                        # 履歴データ → hist_data
                        hist_data[0][TIME_TB.index(created_time)] = int(e_energy / UNIT)

                    # 表示
                    draw_collect_range(collect, created)
                    draw_monthly_e_energy(monthly_e_energy)
                    draw_monthly_charge(charge)

                else:
                    retries += 1

            check_timeout(inst_time)  # スマートメーターからのデータのタイムアウト判定
            
            # 【RCEV】 子機からデータを受信(ESP NOW)

            d = espnow.recv_data()
            
            if (len(d[2]) > 0):
                key = str(d[2].decode().strip())
                logger.info('[RECV] <- Key = [%s]', key)

                # # 【UNIT】 UNIT を子機に送信する場合
                # # 'UNIT' 積算電力量-[単位x係数]のリクエストに応答
                # if key.startswith('UNIT'):
                #     unit_flag, unit_count = send_unit(unit_flag, unit_count)

                # 【HIST】 'REQ' 積算電力量-履歴データのリクエストに応答
                if key.startswith('REQ'):
                    id = int(key[3:5])
                    
                    if id == 0:
                        cumul_flag = False
                        cumul_time = utime.time() - 1200

                        # 取得済みの履歴データを一気に子機に送信する場合。送信中は瞬時計測値等は更新しない
                        # if hist_flag[0] is True:
                        #     id, hist_time = send_all_hist_data(id)

                    # 指定秒数以内の重複リクエストはスキップ
                    if hist_flag[id] is True and utime.time() - hist_time[id] > 30:
                        _send_data = ''
                        for k in range(0, 49):
                            _send_data += '{:08X}'.format(hist_data[id][k])
                        send_data = (bytes('M:ID{:02}{}{:5}'
                                           .format(id, hist_created[id], hist_date[id]), 'UTF-8')
                                     + binascii.unhexlify(_send_data + '00'))
                        espnow.broadcast(data=send_data)
                        hist_time[id] = utime.time()

                        logger.info('[HIST] -> [(%d) %s [%s %.1f - %.1f : %.1f]]',
                                    id, hist_created[id],
                                    hist_date[id],
                                    hist_data[id][0] * UNIT,
                                    hist_data[id][47] * UNIT,
                                    hist_data[id][48] * UNIT)
                        logger.debug('[HIST] -> Raw = %s', hist_data[id])
                        # logger.debug('[HIST] -> [%d, %s]', id, binascii.hexlify(send_data).decode('utf-8'))

                check_timeout(inst_time)  # スマートメーターからのデータのタイムアウト判定

            # 【HIST】 履歴データを順に取得する
            if hist_flag[hist_day] is False:
                if hist_day == 0:
                    init_time = utime.time()
                try:
                    (_created, _data) = bp35a1.get_hist_cumul_e_energy(hist_day + day_shift)
                    _created_date = _created[:10]
                    _created_time = _created[11:16]

                    if _created_time == '00:00' and day_shift == 0:
                        day_shift = 1

                    elif hist_flag[hist_day] is False:   # 要求日のデータが存在しなければ、受信処理
                        for k in range(0, 48):
                            if int(_data[(k * 8):(k * 8) + 8], 16) > 0x05f5e0ff:  # =99999999
                                hist_data[hist_day][k] = 0
                            else:
                                hist_data[hist_day][k] = int(_data[(k * 8):(k * 8) + 8], 16)
                        hist_created[hist_day] = _created
                        hist_date[hist_day] = date_of_days_ago(_created_date, hist_day + day_shift)
                        hist_flag[hist_day] = True

                        logger.info('[HIST] <= BP35A1: [(%d) %s [%s %.1f - %.1f : %.1f]]',
                                    hist_day, hist_created[hist_day],
                                    hist_date[hist_day],
                                    hist_data[hist_day][0] * UNIT,
                                    hist_data[hist_day][47] * UNIT,
                                    hist_data[hist_day][48] * UNIT)
                        logger.debug('[HIST] <= BP35A1: Raw = %s', hist_data[hist_day])

                        if hist_day < data_period:
                            hist_data[hist_day + 1][48] = hist_data[hist_day][0]
                            hist_day += 1

                        else:
                            beep()
                            t =utime.time() - init_time
                            logger.info('[HIST] Data acquisition completed. time = %d', t)
                            indicator_timer.deinit()
                            lcd.circle(234, 7, 3, 0x000000, 0x000000)

                        retries = 0

                except Exception as e:
                    logger.error('[HIST] %s', e)
                    hist_flag[hist_day] = False
                    retries += 1

            check_timeout(inst_time)  # スマートメーターからのデータのタイムアウト判定

            # 【AMBIENT】 Ambientデータ送信：Send every config['A_INTERVAL'] seconds
            if (utime.time() - ambient_time) >= config['A_INTERVAL']:
                result = send_ambient()
                ambient_time = utime.time()
                if result is True:
                    retries = 0
                else:
                    retries += 1

            # 【PING】 動作確認：Ping every 1 hour
            if (utime.time() - ping_time) >= (60 * 60):
                logger.info('[SYS_] Ping BP35A1')
                bp35a1.skPing()
                ping_time = utime.time()
                        
            gc.collect()
            # utime.sleep(0.5)
            # print('[SYS_] mem_free = {} byte'.format(gc.mem_free()))

    except Exception as e:
        logger.error('[ERR.] == Final Exception ==: %s', e)

    finally:
        logger.critical('[SYS_] == system reset ==')
        reset()
