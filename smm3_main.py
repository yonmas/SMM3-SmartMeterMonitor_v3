from m5stack import lcd, btnA
import binascii
import espnow
import logging
import machine
import ntptime
import utime
import wifiCfg
import sys
from bp35a1 import BP35A1
from calc_charge import CalcCharge
import func_main as cnfg
from func_main import beep, status

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
    'COLLECT_CALENDER': [''] * 13,
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
data_period = 30            # 何日前までのデータを参照するか
data_mute = False
ampere_limit_over = False

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


# 【exec】　スクリーン上下反転
def flip_lcd_orientation():
    global orient

    if orient == lcd.LANDSCAPE:
        orient = lcd.LANDSCAPE_FLIP
    else:
        orient = lcd.LANDSCAPE

    logger.info('Set screen orientation: %s', orient)
    lcd.clear()
    lcd.orient(orient)
    draw_main()
    beep()


# 【exec】　WiFi接続チェック
def checkWiFi(arg):
    if not wifiCfg.is_connected():
        logger.warn('Reconnect to WiFi')
        if not wifiCfg.reconnect():
            logger.warn('Rest')
            machine.reset()


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
        espnow.broadcast(data=str('TOUT'))  # ESP NOW で timeout を子機に通知


# 【exec】　積算電力量-履歴データを取得
def get_hist_data(n):
    (created, history_of_e_energy) = bp35a1.get_hist_cumul_e_energy(n)
    hist_data = (bytes('ID{:02}{}'.format(n, created), 'UTF-8')
                 + binascii.unhexlify(history_of_e_energy))
    return hist_data


# 【config】　インスタンスの設定
def set_instance(config):
    global bp35a1, ambient_client, logger, calc_charge_func

    status('Create objects', uncolor)
    bp35a1 = BP35A1(config['B_ID'],
                    config['B_PASSWORD'],
                    config['COLLECT_CALENDER'],
                    ipv6_addr,
                    coefficient,
                    unit,
                    progress_func=progress,
                    log_level=config['LOG_LEVEL'])
    logger.info('[INIT] BP35A1 config: (%s, %s, %s)', config['B_ID'],
                config['B_PASSWORD'], config['COLLECT_CALENDER'])

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

    logger.setLevel(eval('logging.{}'.format(config['LOG_LEVEL'])))
    logger.info('[INIT] Logging level = %s', config['LOG_LEVEL'])


# 【config】　設定用GSSから設定をリロード
def reload_config(config):
    global TIMEOUT_MAIN, WARNING_AMPERAGE, CONTRACT_AMPERAGE
    global inst_time, cumul_time, cumul_flag

    lcd.clear()
    status('Reloading config from GSS.', uncolor)

    config = cnfg.update_config_from_gss(api_config, config)
    cnfg.save_config(config)
    config, TIMEOUT_MAIN, WARNING_AMPERAGE, CONTRACT_AMPERAGE = cnfg.set_config(config)
    set_instance(config)
    draw_main()
    beep()

    inst_time = utime.time() - 120  # INST タイマー
    cumul_time = utime.time() - 120  # CUML タイマー
    cumul_flag = False


# 【send】 'UNIT' 積算電力量-[単位x係数]のリクエストに応答
def send_unit(unit_flag, unit_count):
    if unit_flag is False:
        espnow.broadcast(data=str('UNT=' + str(unit * coefficient)))
        unit_flag = True
        logger.info('[UNIT] >> %.1f', unit * coefficient)
    else:
        unit_count += 1
        logger.debug('[UNIT] Skip UNIT Request: counter = %d', unit_count)
        if unit_count >= 10:  # 最大リトライ回数
            unit_count = 0
            unit_flag = False
            logger.debug('[UNIT] Reset UNIT Counter')

    return unit_flag, unit_count


# 【send】 'REQ' 積算電力量-履歴データのリクエストに応答
def send_hist(hist_flag, unit_flag, unit_count, n):
    if hist_flag[n] == 0:
        try:
            hist_data = get_hist_data(n)
            espnow.broadcast(data=hist_data)
            hist_flag[n] += 1
            _hist_data = binascii.hexlify(hist_data[23:]).decode('utf-8')
            _hist_data_00 = round(int(_hist_data[:8], 16) * unit * coefficient, 1)
            if int(_hist_data[-8:], 16) <= 0x05f5e0ff:
                _hist_data_47 = round(int(_hist_data[-8:], 16) * unit * coefficient, 1)
            else:
                _hist_data_47 = 0.0
            logger.info('[HIST] >> (%d) = [%s, [%s - %s]]', n, hist_data[4:23].decode('utf-8'),
                        str(_hist_data_00), str(_hist_data_47))
            logger.debug('[HIST] >> Raw(%d) = [%s]', n, _hist_data)

        except Exception as e:
            logger.error('[HIST] %s', e)
            hist_flag[n] = 0

    else:  # リクエスト応答後に届く重複リクエストを規定回数スキップする
        hist_flag[n] += 1
        logger.debug('[HIST] Skip REQ(%d) Request: counter = %d', n, hist_flag[n])
        if hist_flag[n] >= 5:  # 最大スキップ回数
            hist_flag[n] = 0  # 規定回数スキップしてもリクエストが届くときはフラグをクリアして再応答
            logger.debug('[HIST] Reset REQ(%d) Counter', n)

    return hist_flag, unit_flag, unit_count


# 【send】 積算電力量　取得 ＆ 表示 & 子機送信
def send_cumul():
    logger.debug('\n[CUML] == Monthly e-Energy & Monthly Charge ==')

    result = False
    _collect = collect
    _created = created
    _monthly_e_energy = monthly_e_energy
    _charge = charge

    try:
        # 取得
        (_collect, _monthly_e_energy, _created, _e_energy) = bp35a1.get_monthly_e_energy()
        _charge = calc_charge_func(config['CONTRACT_AMPERAGE'], _monthly_e_energy)

        # 子機送信
        CUML = str('CUML' + str(_e_energy) + '/' + str(_created) + '/' + str(_collect) + '/'
                   + str(_monthly_e_energy) + '/' + str(_charge))
        espnow.broadcast(data=CUML)
        logger.info('[CUML] >> [%s]', str(CUML))

        result = True

    except Exception as e:
        logger.error('[CUML] %s', e)

    return _collect, _created, _monthly_e_energy, _charge, result


# 【send】 瞬時電力・瞬時電流　取得 ＆ 表示 ＆ 子機送信
def send_inst():
    logger.debug('\n[INST] == Wattage & Amperage ==')

    result = False
    _wattage = wattage
    _amperage = amperage

    try:
        # 取得
        (_, _wattage) = bp35a1.get_instantaneous_wattage()
        utime.sleep(1)
        (_, _amperage) = bp35a1.get_instantaneous_amperage()

        # 子機送信：瞬時電力、瞬時電力発信
        espnow.broadcast(data=str('INST' + str(_wattage) + '/' + str(_amperage)))
        logger.info('[INST] >> [%s , %s]', str(_wattage), str(_amperage))

        result = True

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


if __name__ == '__main__':

    try:
        # logger 初期化
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)  # 初期値 INFO

        # WiFi　&ESP-NOW 設定
        lcd.orient(lcd.PORTRAIT_FLIP)
        wifiCfg.autoConnect(lcdShow=True)
        wifiCfg.wlan_ap.active(True)
        espnow.init(0)

        # Start checking the WiFi connection
        machine.Timer(0).init(period=60 * 1000, mode=machine.Timer.PERIODIC, callback=checkWiFi)

        lcd.clear()
        lcd.orient(orient)
        status('Welcome to SMM3 !', uncolor)

        # 定数の読み込み（ファイル、Googleスプレッドシート）
        status('Load configuration', uncolor)
        config = cnfg.update_config_from_file(config)
        api_config = cnfg.get_api_config()
        config = cnfg.update_config_from_gss(api_config, config)
        cnfg.save_config(config)
        config, TIMEOUT_MAIN, WARNING_AMPERAGE, CONTRACT_AMPERAGE = cnfg.set_config(config)
        set_instance(config)

        # RTC設定（時刻設定）
        status('Set Time', uncolor)
        ntp = ntptime.client(host='jp.pool.ntp.org', timezone=9)

        # ボタン検出スレッド起動
        # Aボタン       スクリーン上下反転
        # Aボタン長押し  GSS から config リロード

        btnA.wasReleased(flip_lcd_orientation)
        btnA.pressFor(0.8, lambda config=config: reload_config(config))

        # Connecting to Smart Meter
        status('Connecting SmartMeter', uncolor)
        (channel, pan_id, mac_addr, lqi, ipv6_addr, coefficient, unit) = bp35a1.open()
        logger.info('[INIT] Connected. BP35A1: (%s, %s, %s, %s, %s)',
                    channel, pan_id, mac_addr, lqi, ipv6_addr)

        # Start monitoring
        status('Start monitoring', uncolor)

        # 親機起動を通知
        espnow.broadcast(data='BOOT')
        utime.sleep(0.1)
        # espnow.broadcast(data=str('UNT=' + str(unit*coefficient)))

        # データ取得処理
        hist_flag = [1] * (data_period + 2)
        cumul_flag = False

        # << unit*coefficient を子機に送信する場合
        unit_flag = True
        unit_count = 0

        # 表示値初期値
        wattage = 0
        amperage = 0
        monthly_e_energy = 0
        charge = 0
        collect = '****-**-** **:**:**'
        created = '****-**-** **:**:**'

        # タイマー処理
        inst_time = utime.time() - 120  # INST タイマー
        cumul_time = utime.time() - 120  # CUML タイマー
        ambient_time = utime.time() - 120  # Ambient タイマー
        ping_time = utime.time() - 120  # ping タイマー

        # 画面初期化
        lcd.clear()
        draw_main()
        # status('Please wait a moment.', uncolor)

        retries = 0  # リトライカウンター

        # メインループ
        while retries < max_retries:

            # 子機からデータを受信(ESP NOW)
            d = espnow.recv_data()
            key = str(d[2].decode())
            if key != '':
                logger.info('[RECV] << Key = [%s]', key)

            # # << unit*coefficient を子機に送信する場合
            # # 'UNIT' 積算電力量-[単位x係数]のリクエストに応答
            # if key.startswith('UNIT'):
            #     unit_flag, unit_count = send_unit(unit_flag, unit_count)
            unit_flag = True  # << unit*coefficient を子機に送信する場合はコメントアウト

            # 'REQ' 積算電力量-履歴データのリクエストに応答
            if key.startswith('REQ'):
                n = int(key[3:5])
                if (n == 0) and (hist_flag[1] != 0) and (unit_flag is True):
                    hist_flag = [0] * (data_period + 2)
                    cumul_flag = False
                    cumul_time = utime.time() - 120
                    # unit_flag = False
                    # unit_count = 0

                hist_flag, unit_flag, unit_count = send_hist(hist_flag, unit_flag, unit_count, n)

            check_timeout(inst_time)  # スマートメーターからのデータのタイムアウト判定

            # 積算電力量　取得 ＆ 表示 & 子機送信：Updated every 10 minutes
            if (((utime.localtime()[4] % 10 == 0) and (utime.time() - cumul_time >= 60))
                    or ((cumul_flag is False) and (utime.time() - cumul_time >= 60))):
                utime.sleep(3)
                cumul_flag = False
                collect, created, monthly_e_energy, charge, result = send_cumul()
                cumul_time = utime.time()
                if result is True:
                    retries = 0
                    cumul_flag = True

                    # 表示
                    draw_collect_range(collect, created)
                    draw_monthly_e_energy(monthly_e_energy)
                    draw_monthly_charge(charge)

                else:
                    retries += 1

            check_timeout(inst_time)  # スマートメーターからのデータのタイムアウト判定

            # 瞬時電力・瞬時電流　取得 ＆ 表示 ＆ 子機送信：Updated every 10 seconds
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

            # Ambientデータ送信：Send every config['A_INTERVAL'] seconds
            if (utime.time() - ambient_time) >= config['A_INTERVAL']:
                result = send_ambient()
                ambient_time = utime.time()
                if result is True:
                    retries = 0
                else:
                    retries += 1

            # 動作確認：Ping every 1 hour
            if (utime.time() - ping_time) >= (60 * 60):
                logger.info('[SYS_] Ping BP35A1')
                bp35a1.skPing()
                ping_time = utime.time()

            utime.sleep(1)
            # print('[SYS_] mem_free = {} byte'.format(gc.mem_free()))

    except Exception as e:
        logger.error('[ERR.] == Final Exception ==: %s', e)

    finally:
        logger.info('[SYS_] == system reset ==')
        machine.reset()
