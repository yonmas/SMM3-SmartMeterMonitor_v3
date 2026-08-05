from m5stack import lcd, btnA, btnB
from machine import Timer, reset, WDT, reset_cause
import array
import binascii
import espnow
import gc
import logging
import math
import ntptime
import sys
import ujson
import urequests
import usocket
import ussl
import utime
import wifiCfg
from bp35a1 import BP35A1
from calc_charge import CalcCharge
from func_main import beep, status
import func_main as cnfg

# Web ダッシュボード (Google Apps Script) 設定
# GAS の /exec URL は秘匿情報（漏れると宅内電力データの閲覧＋偽データPOSTが可能）なのでコードに
# 直書きせず、config['WEB_GAS_URL']（config_main.json / 設定用GSS）から起動時に読み込む。
# 空（未設定）なら GAS への送信はすべてスキップされる（_web_post が no-op）。
WEB_GAS_URL = ''
WEB_INST_INTERVAL = 30  # 瞬時電力をGASへ送る間隔（秒）。ESP-NOW(10秒)より粗くしてGAS無料枠を節約
WEB_HIST_SEND_ENABLED = True  # 履歴データのGAS送信。H2検証で送信有りに復帰（cuml/instの瞬時送信は対象外）
BLACKBOX_ENABLED = True  # 起動時に reset_cause を GAS へ報告（type:'boot'）。GAS側で累積再起動回数＋
                         # タイムスタンプ付きログを恒久保存し、再起動頻度を把握する。Falseで報告OFF
                         # （実行時の動きだけ止まる。RTCは本機で再起動を跨がず不可のためGAS側で記録する）。
WEB_POST_TIMEOUT = 15  # GAS送信ソケットのtimeout(秒)。settimeoutは各操作(connect/write/read)ごとの制限。
                       # 危険なのはレスポンスread＝サーバがシート追記して返すまで待つ所。正常は〜5秒だが
                       # コールドスタート/シート混雑で伸びうるため15秒に余裕を持たせる。ハングは約15秒で
                       # 例外化(ETIMEDOUT)→呼び出し側try/exceptが拾い再起動せず復帰。切りすぎるなら延ばす。
WDT_TIMEOUT_MS = 120000  # ハードウォッチドッグ周期(ms)。urequestsがGAS無応答で無限ブロックしてもfeedが途切れて
                         # 約120秒で自動リセット→復帰。BP35A1の最大待ち(~60s)＋sleep(30)を上回る値で誤リセットを回避。

# 定数初期値
config = {
    'B_ID': None,
    'B_PASSWORD': None,
    'A_ID': '*',
    'A_KEY': '*',
    'WEB_GAS_URL': '',   # GASダッシュボードの /exec URL（Ambientの A_ID/A_KEY の後継＝データ送信先）
    'A_INTERVAL': 30,
    'CONTRACT_AMPERAGE': 40,
    'WARNING_AMPERAGE': 30,
    'COLLECT_MONTH': [12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    'COLLECT_CALENDAR': [''] * 13,
    'COLLECT_DATE': 15,
    'CHARGE_FUNC': 'tepco',
    'BASE': 1247.00,
    'RATE1': 29.80,
    'RATE2': 36.40,
    'RATE3': 40.49,
    'NENCHO': 0,
    'SAIENE': 0,
    'TIMEOUT_MAIN': 30,
    'LOG_LEVEL': 'INFO',  # 'CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'
}

# Global variables #
logger = None               # Logger object
logger_name = 'MAIN'        # Logger name
bp35a1 = None               # BPA35A1 object
ipv6_addr = None
coefficient = None
unit = None
orient = lcd.LANDSCAPE      # Display orientation
max_retries = 30            # Maximum number of times to retry
data_mute = False
ampere_limit_over = False
step = 0
hist_retry_queue = []       # Web送信に失敗した(日, half)。メインループ1回につき1件だけ再送信を試みる
web_oom_count = 0           # ⓐ自己復旧：履歴取得後のweb送信(inst/cuml)の連続MemoryError数（成功で0）
WEB_OOM_RESET = 6           # ⓐ自己復旧：この回数連続でMemoryErrorなら断片化と判断（→本来はリセット）
web_recovery_pending = False  # ⓐ自己復旧：トリガー条件成立フラグ。今は検知のみ（reset実行は担保＝未実行）
wdt = None                  # ハードウォッチドッグ。履歴取得完了＝定常運転入り後に初めて生成（起動フェーズは非監視）

# タイマー
checkWiFi_timer = Timer(0)
indicator_timer = Timer(3)

# 履歴データを取得する期間（日）
data_period = 13            # 何日前までのデータを参照するか

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


# 【STEP0】 起動時/履歴取得後の最大連続ブロックを二分探索で実測（gc.mem_free()の総量は断片化を見せないため）
def probe_largest_block():
    gc.collect()
    total = gc.mem_free()
    lo, hi, best = 0, total, 0
    while lo <= hi:
        mid = (lo + hi) // 2
        try:
            b = bytearray(mid)
            del b
            best = mid
            lo = mid + 1
        except MemoryError:
            hi = mid - 1
    gc.collect()
    return total, best  # 整数2値だけ返す（文字列化は呼び出し側でログ出力時に行う）


# 【calc】　day[yyyy-mm-dd] から 曜日番号を返す　（0:月, 1:火, 2:水, 3:木, 4:金, 5:土, 6:日）
def day_from_date(date_str):
    [yyyy, mm, dd] = [int(i) for i in date_str.split('-')]
    the_date = (yyyy, mm, dd, 1, 0, 0, 0, 0, 0)
    day = int((utime.mktime(the_date) // 86400) - 10957) % 7
    return day


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

    # H1.5:logger.info('[EXEC] Flip screen.')

    if orient == lcd.LANDSCAPE:
        orient = lcd.LANDSCAPE_FLIP
    else:
        orient = lcd.LANDSCAPE

    lcd.orient(orient)
    draw_main()
    beep()


# 【exec】　WiFi接続チェック
def checkWiFi(arg):
    # H1.5:logger.info('[EXEC] Checking Wi-Fi.')
    if not wifiCfg.is_connected():
        # H1.5:logger.warning('[ERR.] Reconnect to WiFi')
        if not wifiCfg.reconnect():
            # H1.5:logger.warning('[SYS_] == system reset ==')
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
    if wdt is not None:
        wdt.feed()  # ループ内の各ステージ境界でWDTに餌やり（正常動作中は必ずここを通る／ハング中は通らない）
    if ((utime.time() - inst_time) >= TIMEOUT_MAIN) and (data_mute is False):
        data_mute = True
        draw_wattage(wattage)
        draw_amperage(amperage)
        espnow.broadcast(data=str('M:TOUT'))  # ESP NOW で timeout を子機に通知


# 【config】　インスタンスの設定
def set_instance(config):
    global bp35a1, logger, calc_charge_func

    status('Create objects', uncolor)
    bp35a1 = BP35A1(config['B_ID'],
                    config['B_PASSWORD'],
                    config['COLLECT_CALENDAR'],
                    ipv6_addr,
                    coefficient,
                    unit,
                    progress_func=progress,
                    log_level=config['LOG_LEVEL'])
    # H1.5:logger.info('[INIT] BP35A1 config: (%s, %s, %s)', config['B_ID'],
                # H1.5:config['B_PASSWORD'], config['COLLECT_CALENDAR'])

    calc_instance = CalcCharge(
        config['BASE'],    # 基本料金
        config['RATE1'],   # 1段料金
        config['RATE2'],   # 2段料金
        config['RATE3'],   # 3段料金
        config['NENCHO'],  # 燃料費調整単価
        config['SAIENE'],  # 再エネ発電賦課金単価
        1                  # 前日までの集計
    )

    try:
        calc_charge_func = getattr(calc_instance, config['CHARGE_FUNC'])
    except Exception as e:
        status('No calc_charge_method !', 0xff0000)
        # H1.5:logger.error('[INIT] %s', e)
        beep()
        utime.sleep(30)
        sys.exit()

    # H1.5:logger.info('[INIT] Charge Function: %s', calc_charge_func.__name__)

    # H1.5:log_level = getattr(logging, config['LOG_LEVEL'], None)
    # H1.5:logging.basicConfig(level=log_level)
    # H1.5:logger.info('[INIT] Logging level = %s', config['LOG_LEVEL'])


# 【config】　設定用GSSから設定をリロード
def reload_config(config):
    global TIMEOUT_MAIN, WARNING_AMPERAGE, CONTRACT_AMPERAGE
    global collect, monthly_e_energy, charge
    global WEB_GAS_URL
    # global inst_time, cumul_time, cumul_flag

    lcd.clear()
    status('Reloading config from GSS.', uncolor)

    config = cnfg.update_config_from_gss(api_config, config)
    cnfg.save_config(config)
    WEB_GAS_URL = config.get('WEB_GAS_URL', '')  # GSSでURLが変わっていれば送信先も更新
    _set_web_endpoint()
    config, TIMEOUT_MAIN, WARNING_AMPERAGE, CONTRACT_AMPERAGE = cnfg.set_config(config)
    set_instance(config)  # インスタンスを再定義
    collect, _, _, monthly_e_energy, charge, _ = send_cumul()  # 料金を再計算
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
        # H1.5:logger.info('[UNIT] -> %.1f', UNIT)
    else:
        unit_count += 1
        # H1.5:logger.debug('[UNIT] Skip UNIT Request: counter = %d', unit_count)
        if unit_count >= 10:  # 最大リトライ回数
            unit_count = 0
            unit_flag = False
            # H1.5:logger.debug('[UNIT] Reset UNIT Counter')

    return unit_flag, unit_count


# 【send】 積算電力量　取得 ＆ 表示 & 子機送信
def send_cumul():
    # H1.5:logger.debug('[CUML] == Monthly e-Energy & Monthly Charge ==')

    result = False
    _collect = collect
    _created = created
    _e_energy = e_energy
    _monthly_e_energy = monthly_e_energy
    _charge = charge

    try:
        # 取得
        _created, _e_energy = bp35a1.get_cumul_e_energy()
        _created_date = _created[:10]
        _created_day = day_from_date(_created_date)  # 曜日番号の取得

        _days_ago = data_period
        _col = date_of_days_ago(_created_date, _days_ago).split('/')
        _collect = '****-{:02d}-{:02d}'.format(int(_col[0]), int(_col[1]))

        _hourly_power = [[0 for i in range(24)] for j in range(_days_ago + 1)]
        if hist_flag[_days_ago] is True:  # 料金計算期間のデータを取得済みなら〜
            for i in range(0, _days_ago + 1):  # 1時間ごとの使用電力量リストを作成（料金計算用）
                for j in range(0, 24):
                    if hist_data[i][j * 2 + 2] != 0:
                        _hourly_power[i][j] = (hist_data[i][j * 2 + 2] - hist_data[i][j * 2])
                    elif hist_data[i][j * 2 + 1] != 0:
                        _hourly_power[i][j] = (hist_data[i][j * 2 + 1] - hist_data[i][j * 2])

            _charge, _monthly_e_energy = calc_charge_func(config['CONTRACT_AMPERAGE'],
                                                          _hourly_power, _created_day, UNIT)

            # H1.5:logger.debug('[CUML] -> hourly_power = %s', _hourly_power)
            del _hourly_power
            gc.collect()

        # 子機送信
        CUML = str('M:CUML' + str(_collect) + '/' + str(_created) + '/' + str(_e_energy) + '/'
                   + str(_monthly_e_energy) + '/' + str(_charge))
        espnow.broadcast(data=CUML)
        # H1.5:logger.info('[CUML] -> [%s]', str(CUML))

        # Web ダッシュボード(GAS)へも同じタイミングで送信
        send_web_cuml(_collect, _created, _e_energy, _monthly_e_energy, _charge)

        result = True

    except Exception as e:
        # H1.5:logger.error('[CUML] %s', e)
        pass

    return _collect, _created, _e_energy, _monthly_e_energy, _charge, result


# 【send】 瞬時電力・瞬時電流　取得 ＆ 表示 ＆ 子機送信
def send_inst():
    # H1.5:logger.debug('[INST] == Wattage & Amperage ==')

    result = False
    _wattage = wattage
    _amperage = amperage

    try:
        # 取得
        (_wattage, _amperage) = bp35a1.get_instantaneous_data()

        # 子機送信：瞬時電力、瞬時電力発信
        if isinstance(_wattage, int) and isinstance(_amperage, float):
            espnow.broadcast(data=str('M:INST' + str(_wattage) + '/' + str(_amperage)))
            # H1.5:logger.info('[INST] -> [%s , %s]', str(_wattage), str(_amperage))
            result = True

        else:
            raise Exception('Illeagal data: [' + _wattage + ']-[' + _amperage + ']')

    except Exception as e:
        # H1.5:logger.error('[INST] %s', e)
        pass

    return _wattage, _amperage, result


# 【send】 GASへのPOSTの単一チョークポイント。無応答での無限ブロック（=例外もreturnも出ず
# finally:reset()に到達できない唯一のフリーズ経路）を settimeout で断つ。
# ※urequestsのtimeout=引数は非対応、かつ usocket.socket の差し替え（モンキーパッチ）も不可
#   （このFWでは frozen module の属性を再代入すると urequests 側が 'no attribute socket' で全滅）。
#   →実機実証済みの生プリミティブ（usocket+ussl+settimeout）で自前POSTする。ussl の read は
#   下位ソケットの settimeout を尊重し、無応答は約WEB_POST_TIMEOUT秒で ETIMEDOUT。呼び出し側の
#   try/except が拾い、再起動せず（inst/cumlはスキップ・backfillは再送信キューへ）復帰する。
# WEB_GAS_URL は config 読込後に確定するため、import時ではなく _set_web_endpoint() で host/path を
# 解く。未設定（空）の間は _WEB_HOST が '' のままで、_web_post は no-op になる（送信スキップ）。
_WEB_HOST = ''
_WEB_PATH = ''


def _set_web_endpoint():
    # config['WEB_GAS_URL'] を host / path に分解して _web_post 用グローバルへ格納。
    # 起動時（config読込後）と reload_config（GSSリロード後）から呼ぶ。空URLなら両方 '' に。
    global _WEB_HOST, _WEB_PATH
    try:
        _p = WEB_GAS_URL.split('/', 3)
        _WEB_HOST = _p[2]                # 'script.google.com'
        _WEB_PATH = '/' + _p[3]         # '/macros/s/..../exec'
    except Exception:
        _WEB_HOST = ''
        _WEB_PATH = ''


class _WebResp:
    # 呼び出し側は response.close() を呼ぶだけ（status_codeは未使用）
    def close(self):
        pass


def _web_post(payload):
    # WEB_GAS_URL 未設定(config読込失敗・空文字等)を「成功扱いで送信スキップ」にすると、実際には
    # 一切送信していないのに呼び出し元が延々と「OK」と表示し続け、異常に気づけない（2026-08-01夜、
    # 実機でこれが原因の長時間サイレント障害を確認済み）。未設定は例外にして呼び出し元の
    # except節（既存のリトライ/エラーカウント経路）に必ず引っ掛ける。
    if not _WEB_HOST:
        raise OSError('WEB_GAS_URL not set')
    ai = usocket.getaddrinfo(_WEB_HOST, 443)[0][-1]
    so = usocket.socket()
    so.settimeout(WEB_POST_TIMEOUT)
    try:
        so.connect(ai)
        try:
            ss = ussl.wrap_socket(so, server_hostname=_WEB_HOST)
        except TypeError:
            ss = ussl.wrap_socket(so)   # server_hostname 非対応FW向けフォールバック
        req = ('POST ' + _WEB_PATH + ' HTTP/1.0\r\n'
               + 'Host: ' + _WEB_HOST + '\r\n'
               + 'Content-Type: application/json\r\n'
               + 'Content-Length: ' + str(len(payload)) + '\r\n'
               + 'Connection: close\r\n\r\n' + payload)
        ss.write(req.encode())
        ss.read(32)   # 応答の頭を読む＝doPost処理(シート追記/PROP更新)完了を確認。無応答はsettimeoutで例外化
        try:
            ss.close()
        except Exception:
            pass
        return _WebResp()
    finally:
        try:
            so.close()
        except Exception:
            pass


# 【send】 起動時に reset_cause を GAS へ報告（type:'boot'）。GAS側で累積再起動回数＋タイムスタンプ
# ログを恒久保存し、再起動頻度を把握する。本機はRTCが再起動を跨がないためGAS側が記録の本体。
# best-effort（1回・失敗しても起動を止めない）。
def _send_boot_report():
    if not BLACKBOX_ENABLED:
        return
    try:
        _cause = reset_cause()
        resp = _web_post(ujson.dumps({'type': 'boot', 'cause': _cause}))
        resp.close()
        print('[BOOT] reported cause=%d' % _cause)
    except Exception as e:
        print('[BOOT] report failed: %s' % e)


# 【send】 Web ダッシュボード(GAS)へ積算電力量データ送信：M:CUMLと同じタイミング
def send_web_cuml(collect, created, e_energy, monthly_e_energy, charge):
    global web_oom_count
    result = False

    print('[NET]cuml')  # [NET_DIAG] WDTハングの犯人特定用マーカー（一時・特定後に削除）
    try:
        payload = ujson.dumps({
            'type': 'cuml',
            'collect': collect,
            'created': created,
            'e_energy': e_energy,
            'monthly_e_energy': monthly_e_energy,
            'charge': charge,
            # 契約アンペアの正本は設定用GSS。GAS側は設定ページでの表示にのみ使う（編集不可）。
            # 10分毎のcumlに相乗りさせるのは、inst(30秒毎)を太らせず、設定変更後も10分以内に
            # 追従できるため。ESP-NOWの M:CUML 文字列は不変なので子機には影響しない。
            'contract': config['CONTRACT_AMPERAGE'],
        })
        response = _web_post(payload)
        response.close()
        result = True
        web_oom_count = 0

    except Exception as e:
        # GASは doPost() 実行後に302リダイレクトを返すため、urequestsが
        # "Redirects not yet supported" 例外を出すが、処理自体は成功している（実機検証済み）
        if 'Redirect' in str(e):
            result = True
            web_oom_count = 0
        else:
            # 履歴取得後(hist_flag[data_period])のMemoryErrorだけ断片化シグナルとして数える
            if isinstance(e, MemoryError) and hist_flag[data_period]:
                web_oom_count += 1
            print('[WEB_] cuml ERR %s: %s' % (type(e).__name__, e))  # backfillと同様エラー内容を可視化(恒久)

    return result


# 【send】 Web ダッシュボード(GAS)へ瞬時電力データ送信：WEB_INST_INTERVAL秒おきに間引き
# muted: スマートメーターからのデータ途絶中（data_mute）かどうか。本体LCDのグレー表示と同じ意味合い
def send_web_inst(wattage, amperage, muted):
    global web_oom_count
    result = False
    mf = gc.mem_free()  # 送信前の空きヒープ（整数で先取り＝送信を汚染しない）

    print('[NET]inst')  # [NET_DIAG] WDTハングの犯人特定用マーカー（一時・特定後に削除）
    try:
        payload = ujson.dumps({'type': 'inst', 'watt': wattage, 'amp': amperage, 'muted': muted})
        response = _web_post(payload)
        response.close()
        result = True
        web_oom_count = 0

    except Exception as e:
        # GASは doPost() 実行後に302リダイレクトを返すため、urequestsが
        # "Redirects not yet supported" 例外を出すが、処理自体は成功している（実機検証済み）
        if 'Redirect' in str(e):
            result = True
            web_oom_count = 0
        else:
            # 履歴取得後(hist_flag[data_period])のMemoryErrorだけ断片化シグナルとして数える
            if isinstance(e, MemoryError) and hist_flag[data_period]:
                web_oom_count += 1
            print('[WEB_] inst ERR %s: %s mf%d' % (type(e).__name__, e, mf))  # backfillと同様エラー内容を可視化(恒久)

    # H1.5:logger.info('[WEB_] inst mf %d/%d oom%d', mf, gc.mem_free(), web_oom_count)
    return result


# 【calc】 hist_date[d]（"M/D"形式・年無し）を、年を補完した"YYYY-MM-DD"に変換する。
# hist_created[d]は「取得した時刻」（≒常に今日）であり、その日のデータの実際の日付ではないため、
# バックフィルの日付には使えない（hist_date[d]の方が正しい日付）
def hist_date_to_full(d):
    today_str = hist_created[0][:10]  # "YYYY-MM-DD"（hist_created[0]は当日分なので今日の日付として使える）
    today_year = int(today_str[:4])
    today_month = int(today_str[5:7])
    today_day = int(today_str[8:10])

    parts = hist_date[d].split('/')
    month = int(parts[0])
    day = int(parts[1])

    year = today_year
    if (month, day) > (today_month, today_day):  # 今日より後の月日なら年をまたいでいる＝前年
        year -= 1

    return '{:04d}-{:02d}-{:02d}'.format(year, month, day)


# 【send】 Web ダッシュボード(GAS)へ履歴データ送信（半日分、BP35A1から取得した直後にその場で送る）
# キューに積んで後でまとめて送ると、子機リクエストの有無に依存したり、履歴取得完了直後に
# 一気に送信が集中したりするため、取得済みの1日分が確定した瞬間にここで送ってしまう。
# 1日分（48点）を一度に送るとペイロード確保がMemoryErrorになりやすいことが実機検証で
# 再確認できたため、半日（24点）ずつ2回に分けて送る（旧backfill_queue方式と同じ粒度）。
# 確定済みの過去日（d>=1）はe_energy==0（メーター交換等でデータが無い時間帯）もスキップせず送る。
# GAS側で交換以前を0埋めとして扱い、現在値との差分計算を交換を挟んでも特別扱いせずに済ませるため。
# 今日（d=0）だけは0を未計測（まだ24時になっていない）として送らない（過去日の0埋めとは別の意味）。
def send_web_hist_half(d, half):
    if not WEB_HIST_SEND_ENABLED:
        return True

    date_str = hist_date_to_full(d)
    points = []
    for k in range(half * 24, half * 24 + 24):
        if d == 0 and hist_data[d][k] == 0:
            continue  # 今日(d=0)はまだ24時になっていない＝未来分の0は「未計測」なので送らない
        time_str = '{:02d}:{:02d}:00'.format(k // 2, (k % 2) * 30)
        points.append({
            'created': date_str + ' ' + time_str,
            'e_energy': round(hist_data[d][k] * UNIT, 1)
        })

    if not points:
        return True  # 送る対象が無い＝再送信の必要も無いので成功扱い

    gc.collect()
    mf = gc.mem_free()  # 送信直前の空きヒープ（整数で先取り＝核心のTLS確保を汚染しない。文字列ログは送信後）
    _bf_total, _bf_largest = probe_largest_block()
    print('[BF] d%d half%d pre total=%d largest=%d' % (d, half, _bf_total, _bf_largest))  # [BF_TREND]

    try:
        payload = ujson.dumps({'type': 'backfill', 'points': points})
        response = _web_post(payload)
        response.close()
        print('[BF] d%d half%d OK %dpt' % (d, half, len(points)))  # [BF_TREND]
        return True

    except Exception as e:
        if 'Redirect' in str(e):
            print('[BF] d%d half%d OK(redirect) %dpt' % (d, half, len(points)))  # [BF_TREND]
            return True
        else:
            print('[BF] d%d half%d ERR %s mf%d' % (d, half, type(e).__name__, mf))  # [BF_TREND]
            return False


def send_web_hist_day(d):
    if not send_web_hist_half(d, 0):
        hist_retry_queue.append((d, 0))
    if not send_web_hist_half(d, 1):
        hist_retry_queue.append((d, 1))


# 【send】 送信失敗した(日, half)の再送信。メインループ1回につき1件だけ試し、
# 失敗したら末尾に戻して次の機会にまた試す（即時リトライだとヒープ状態が変わらず
# 同じ理由で再失敗し続けるだけなので、他の処理を挟んで断片化レイアウトが変わる
# 機会を待つ。データ欠損を許容しないため回数上限は設けない）。
def send_web_hist_retry_one():
    if not hist_retry_queue:
        return

    d, half = hist_retry_queue.pop(0)
    if not send_web_hist_half(d, half):
        hist_retry_queue.append((d, half))


# 【exec】　積算電力-履歴データ取得
def get_hist_data():
    global hist_day, hist_flag, hist_created, hist_date, hist_data, day_shift, cumul_flag
    global hist_time, cumul_time, web_oom_count

    # H1.5:logger.info('[INIT] Get Historical DATA')
    web_oom_count = 0  # ⓐ再取得開始時にリセット（取得中は誤発火させない。hist_flag[data_period]もFalseに戻る）

    del hist_data

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


if __name__ == '__main__':

    try:
        # logger 初期化
        # H1.5:logging.basicConfig(level=logging.INFO)
        # H1.5:logger = logging.getLogger(logger_name)

        # WiFi　&ESP-NOW 設定
        lcd.orient(orient)  # 横向き（純正のWiFi画面を使わないので縦向きにする必要が無い）
        lcd.clear()
        # WiFi接続：接続できるまで自動リトライする。従来の autoConnect(lcdShow=True) は失敗時に
        # UIFlowのオレンジ再接続画面でボタン待ち＝停止してしまうため、lcdShow=Falseで自前ループにする。
        # 画面表示は起動時の他メッセージと同じ status()（横向き・中央、シリアルにも[STAT]で出る）に揃える。
        # 初回は "retry" と出さない（1回目の接続はリトライではないため）。
        _wifi_try = 0
        while not wifiCfg.is_connected():
            _wifi_try += 1
            if _wifi_try == 1:
                status('Connecting WiFi...', uncolor)
            else:
                status('WiFi retry #%d' % (_wifi_try - 1), uncolor)
            try:
                wifiCfg.autoConnect(lcdShow=False)
            except Exception as _e:
                print('[WiFi] err %s' % _e)
            _t = 0
            while _t < 8 and not wifiCfg.is_connected():
                utime.sleep(1)
                _t += 1
        wifiCfg.wlan_ap.active(True)
        espnow.init(0)

        # Start checking the WiFi connection
        checkWiFi_timer.init(period=60 * 1000, mode=checkWiFi_timer.PERIODIC, callback=checkWiFi)

        lcd.clear()
        lcd.orient(orient)
        status('Welcome to SMM3-lite !', uncolor)

        # 定数の読み込み（ファイル、Googleスプレッドシート）
        # ファイル読込(ローカルI/Oのみ・ネットワーク無し)の直後に GAS送信先を確定してboot報告を送る。
        # GSS読込(get_api_config/update_config_from_gss、urequestsでのネットワークGET)より前に置くのは、
        # config化前の「WiFi接続直後にboot報告」に近い性質を保つため（他のネットワーク処理より先に
        # GASへの最初の接続を試みる）。なお2026-08-01夜の障害調査では、この順序自体は原因ではなく、
        # 真因は WEB_GAS_URL が config_main.json から空で読み込まれていたこと（検証用に別バージョンを
        # 交互デプロイした際、save_config()がWEB_GAS_URLキー無しの状態で上書き保存してしまっていた）
        # と判明した。空URL時に_web_postが例外を出さず黙って成功扱いを返していたため長時間気づけな
        # かった（_web_post側は修正済み、下記参照）。
        config = cnfg.update_config_from_file(config)
        WEB_GAS_URL = config.get('WEB_GAS_URL', '')
        _set_web_endpoint()
        _send_boot_report()  # 起動報告（GASで再起動回数/頻度を把握）。URL未設定なら no-op。

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
        # H1.5:logger.info('[INIT] Connected. BP35A1: (%s, %s, %s, %s, %s)',
                    # H1.5:channel, pan_id, mac_addr, lqi, ipv6_addr)

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
        ping_time = utime.time() - 1200  # ping タイマー
        web_inst_time = utime.time() - 1200  # Web 瞬時電力 タイマー
        
        # 画面初期化
        lcd.clear()
        draw_main()
        indicator_timer.deinit()
        indicator_timer.init(period=200, mode=indicator_timer.PERIODIC, callback=draw_indicator)

        retries = 0  # リトライカウンターリセット

        _total, _largest = probe_largest_block()
        print('[WEB_] mem at boot (before main loop): total=%d largest=%d' % (_total, _largest))  # [STEP0][A]

        # ※ハードウォッチドッグ(wdt)は「履歴取得が完了して定常運転に入った後」に初めて生成する（下の完了分岐）。
        #   起動時の履歴取得はフラッキーなメーターや起動直後のネットワーク一斉送信で正当に120s超のことがあり、
        #   ここで生成するとWDTが誤発火→リセット→また履歴取得の頭でハマる＝ブートループになるため。
        #   報告されたフリーズは定常運転中(数日に1回)のGAS送信で発生しており、そこだけ守れば十分。

        # メインループ
        while retries < max_retries:
            if wdt is not None:
                wdt.feed()  # ループ先頭で毎周feed（定常運転入り＝wdt生成後のみ）

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
                            if hist_day < data_period:
                                hist_day += 1
                            day_shift = 0
                            # H1.5:logger.info('[EXEC] Day-to-Day processed!')
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
                # H1.5:logger.info('[RECV] <- Key = [%s]', key)

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

                        # H1.5:logger.info('[HIST] -> [(%d) %s [%s %.1f - %.1f : %.1f]]',
                                    # H1.5:id, hist_created[id],
                                    # H1.5:hist_date[id],
                                    # H1.5:hist_data[id][0] * UNIT,
                                    # H1.5:hist_data[id][47] * UNIT,
                                    # H1.5:hist_data[id][48] * UNIT)
                        # H1.5:logger.debug('[HIST] -> Raw = %s', hist_data[id])
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
                        if hist_day == 0:
                            hist_data[hist_day][48] = int(_data[:8], 16)
                        day_shift = 1
                        utime.sleep(30)  # スマートメーターの日跨ぎ処理タイムラグを解消するため

                    elif hist_flag[hist_day] is False:   # 要求日のデータが存在しなければ、受信処理
                        for k in range(0, 48):
                            if int(_data[(k * 8):(k * 8) + 8], 16) > 0x05f5e0ff:  # =99999999
                                hist_data[hist_day][k] = 0
                            else:
                                hist_data[hist_day][k] = int(_data[(k * 8):(k * 8) + 8], 16)
                        hist_created[hist_day] = _created
                        hist_date[hist_day] = date_of_days_ago(_created_date, hist_day + day_shift)
                        hist_flag[hist_day] = True

                        # H1.5:logger.info('[HIST] <= BP35A1: [(%d) %s [%s %.1f - %.1f : %.1f]]',
                                    # H1.5:hist_day, hist_created[hist_day],
                                    # H1.5:hist_date[hist_day],
                                    # H1.5:hist_data[hist_day][0] * UNIT,
                                    # H1.5:hist_data[hist_day][47] * UNIT,
                                    # H1.5:hist_data[hist_day][48] * UNIT)
                        # H1.5:logger.debug('[HIST] <= BP35A1: Raw = %s', hist_data[hist_day])

                        send_web_hist_day(hist_day)  # 取得直後にその場でGASへ送信（キュー無し）

                        if hist_day < data_period:
                            hist_data[hist_day + 1][48] = hist_data[hist_day][0]
                            hist_day += 1

                        else:
                            beep()
                            t =utime.time() - init_time
                            # H1.5:logger.info('[HIST] Data acquisition completed. time = %d', t)
                            _total, _largest = probe_largest_block()
                            print('[WEB_] mem after history acquisition: total=%d largest=%d' % (_total, _largest))  # [STEP0][B]
                            indicator_timer.deinit()
                            lcd.circle(234, 7, 3, 0x000000, 0x000000)
                            cumul_flag = False
                            cumul_time = utime.time() - 1200
                            # 定常運転入り：ここで初めてWDT起動（以降のGAS無応答ハングを約120sで検知→復帰）。
                            # 起動フェーズは非監視のままにしてブートループを避ける。
                            if wdt is None:
                                wdt = WDT(timeout=WDT_TIMEOUT_MS)
                                print('[WEB_] WDT armed (steady state)')

                        retries = 0

                except Exception as e:
                    # H1.5:logger.error('[HIST] %s', e)
                    hist_flag[hist_day] = False
                    retries += 1

            check_timeout(inst_time)  # スマートメーターからのデータのタイムアウト判定

            # 【WEB_INST】 Web ダッシュボード(GAS)へ瞬時電力送信：Send every WEB_INST_INTERVAL seconds
            if (utime.time() - web_inst_time) >= WEB_INST_INTERVAL:
                send_web_inst(wattage, amperage, data_mute)
                web_inst_time = utime.time()

            # 【WEB_HIST_RETRY】 履歴データ送信に失敗した(日, half)があれば、メインループ1回につき1件だけ再送信
            if hist_retry_queue:
                send_web_hist_retry_one()

            # 【WEB_RECOVERY】 ⓐ自己復旧（検知のみ・reset実行は担保＝まだ呼ばない）：
            # 履歴取得後にweb送信(inst/cuml)が連続でMemoryError＝ヒープ断片化でGAS盲目化。
            # ambient成功が既存ウォッチドッグ(retries)を無効化するため別系統で検知する。
            # まず実機で「正しいタイミングでフラグが立つか」をログ検証し、確認後にreset()を有効化する。
            if web_oom_count == 0:
                web_recovery_pending = False
            elif (hist_flag[data_period] and web_oom_count >= WEB_OOM_RESET
                  and not web_recovery_pending):
                web_recovery_pending = True
                # H1.5:logger.critical('[WEB_] OOM x%d -> recovery TRIGGER (flag only, reset deferred)',
                                # H1.5:web_oom_count)
                # reset()  # ← 実機でフラグ動作を確認後に有効化する（根治はarray.array化＝別途）

            # 【PING】 動作確認：Ping every 1 hour
            if (utime.time() - ping_time) >= (60 * 60):
                # H1.5:logger.info('[SYS_] Ping BP35A1')
                bp35a1.skPing()
                ping_time = utime.time()
                        
            gc.collect()
            # utime.sleep(0.5)
            # print('[SYS_] mem_free = {} byte'.format(gc.mem_free()))

    except Exception as e:
        # H1.5:logger.error('[ERR.] == Final Exception ==: %s', e)
        pass

    finally:
        # H1.5:logger.critical('[SYS_] == system reset ==')
        reset()
