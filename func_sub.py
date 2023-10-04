from m5stack import *
import uos
import ujson
import utime
import urequests
import ujson
import logging

# 設定ファイル名
API_CONFIG_FILE = '/flash/api_config.json'
CONFIG_FILE = '/flash/config_sub.json'

# 設定用GSSのAPI設定シート情報
BASE_URL = 'https://sheets.googleapis.com/v4/spreadsheets/'
INIT_SPREADSHEET_ID = '1MmbDpG4GTfwRiHsFgsJ89XaIqkVF537lReL4glnOHuc'
INIT_API_KEY = 'AIzaSyAxgp-O2Z0BQSoiHm-6DJCxmldZo4rbQ1g'
INIT_AREA = 'API_config!A1:B4'
INIT_URL = (BASE_URL + INIT_SPREADSHEET_ID + '/values/' + INIT_AREA + '?key=' + INIT_API_KEY)

# 設定用GSSの読み込み範囲（初期値）
SHEET_AREA = 'config!B32:O46'

logger = logging.getLogger('CNFG')
logger.setLevel(logging.INFO)  # 初期値 INFO


# 【exec】　動作音beep
def beep():
    speaker.setVolume(0.1)
    speaker.tone(330, 150)


# 【exec】　処理ステータスの表示
def status(message, *, color=None):
    lcd.font(lcd.FONT_DejaVu18)
    if color is not None:
        lcd.println(message, color=color)
    else:
        lcd.println(message)
    logger.info('[STAT] < %s >', message)


# 【config】　定数 config の読み込み（ファイル）
def update_config_from_file(config):
    try:
        stat_info = uos.stat(CONFIG_FILE)
        with open(CONFIG_FILE, 'r') as f:
            config_from_file = ujson.load(f)
        config.update(config_from_file)
        status('Config_file loaded.')
    except Exception:
        status('Config_file not found !', color=0xff8000)

    return config


# 【config】　API設定用GSSに記入されたAPI初期設定情報をクリアする (Google Apps Script)
def clear_api():
    GAS_KEY = 'AKfycbzijzgzHkNKzn90RiE1UWSdbzIxZKm8aEKvqOhNyvlbNfri3TJcCw8MOZc4RWJ_RjZQ1g'
    URL = 'https://script.google.com/macros/s/' + GAS_KEY + '/exec'
    HEADERS = {'Content-length': '0'}
    req = urequests.post(url=URL, headers=HEADERS)


# 【config】　設定用GSSのAPI設定読み込み
def get_api_config():
    global SHEET_AREA

    api_config = {}

    # Googleスプレッドシートから API設定を読み込む
    try:
        response = urequests.get(INIT_URL)
        api_list = response.json()['values']
        api_config = {item[0]: item[1] for item in api_list}
        api_source = 'gss'
    except Exception:
        api_source = None

    # Googleスプレッドシートから読み込んだ API設定を使用するか確認する
    if api_source == 'gss':
        status('API_GSS loaded.')
        status('Press A-btn for API_GSS.(5s)', color=0xff0000)
        beep()
        utime.sleep(0.1)
        beep()
        api_source = None
        start_time = utime.ticks_ms()
        while utime.ticks_diff(utime.ticks_ms(), start_time) < 5000:
            if btnA.wasPressed():
                status('API_GSS checking.')
                api_source = 'gss'
                utime.sleep(3)
                break

    # Googleスプレッドシートから API設定が読み込めないか、使わないなら、ファイルから読み込む
    if api_source is None:
        status('API_GSS skipped.')
        utime.sleep(3)
        try:
            stat_info = uos.stat(API_CONFIG_FILE)
            with open(API_CONFIG_FILE, 'r') as f:
                api_config = ujson.load(f)
            status('API_file loaded.')
            api_source = 'file'
        except Exception:
            status('API_file not found !', color=0xff8000)
            api_source = None

    # 取得したAPIの有効性チェック　　/ 有効なら　api_config.json に保存
    if api_source is not None:
        URL = (BASE_URL + api_config['SPREADSHEET_ID']
               + '/values/config!A1:A1?key=' + api_config['API_KEY'])
        SHEET_AREA = api_config['SHEET_AREA_S']

        try:
            response = urequests.get(URL)
            d = response.json()['values']
            with open(API_CONFIG_FILE, 'w') as f:
                ujson.dump(api_config, f)
            status('API_file saved.')
            if api_source == 'gss':
                clear_api()  # スプレッドシートの情報を消去
        except Exception:
            # if api_source == 'file':
                # try:
                #     uos.remove(API_CONFIG_FILE)  #
                #     status('API_file removed !', color=0xff8000)
                # except Exception:
                #     pass
            api_config = None

    else:
        api_config = None

    # 設定用GoogleスプレッドシートのAPIを返す. なければ None を返す.
    return api_config


# 【config】　定数 config の読み込み(GSS)
def update_config_from_gss(api_config, config):
    if api_config:
        SPREADSHEET_ID = api_config['SPREADSHEET_ID']
        API_KEY = api_config['API_KEY']
        URL = BASE_URL + SPREADSHEET_ID + '/values/' + SHEET_AREA + '?key=' + API_KEY

        try:
            # APIリクエストを送信し、セルの内容を取得
            response = urequests.get(URL)  # response型
            data_google = response.json()['values']  # 'values'の項目をリスト型として取得
            status('Config_GSS loaded.')

        except Exception:
            status('Config_GSS failure !', color=0xff0000)
            utime.sleep(5)
            return

        # リストの要素が数字の場合、int,floatに変換
        for item in data_google:
            if len(item) != 0:
                key = item[0]
                values = item[1:]

                if len(values) == 1:  # 値がひとつの場合は、単独データ
                    try:
                        if '.' in values[0]:
                            p_val = float(values[0])  # 小数点があればfloat
                        else:
                            p_val = int(values[0])  # 値が数字ならint
                    except ValueError:
                        p_val = values[0]  # そうでなければ値のまま (str)

                elif len(values) > 1:  # 値が2つ以上の場合は、リストとして扱う
                    p_val = []
                    for val in values:
                        try:
                            if '.' in val:
                                p_val.append(float(val))  # 小数点があればfloat
                            else:
                                p_val.append(int(val))  # 値が数字ならint
                        except ValueError:
                            p_val.append(val)  # そうでなければ値のまま (str)

                else:  # 値が無ければ元のまま
                    p_val = config[key]

                config[key] = p_val

    else:
        status('Config_GSS not found !', color=0xff0000)
        beep()
        utime.sleep(3)

    return config


# 【config】　定数 config をファイル保存
def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        ujson.dump(config, f)
    status('Config_file saved.')


# 【config】　定数をセット
def set_config(config):

    DAY_GRAPH_SCALE = config['DAY_GRAPH_SCALE']
    GRAPH_SCALE = config['GRAPH_SCALE']
    BG_COLOR = config['BG_COLOR']
    unit = config['UNIT']

    return DAY_GRAPH_SCALE, GRAPH_SCALE, BG_COLOR, unit
