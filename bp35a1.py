import logging
import machine
import utime
import uos
import ujson

# global variables
logger = None
TIMEOUT_20s = 20
TIMEOUT_60s = 60


# 【decorator】 IOコマンド [コマンド／レスポンス] : DEBUGレベル
def iofunc(func):
    def wrapper(obj, *args):
        if args and not isinstance(args[0], int):
            logger.debug('[WRAP] > [%s]', args[0].strip())
        response = func(obj, *args)
        if (response):
            logger.debug('[WRAP] < [%s]', response.decode().strip())
        # utime.sleep(0.5)
        return response

    return wrapper


# 【decorator】 実行コマンド / 成功 : DEBUGレベル
def skfunc(func):
    def wrapper(obj, *args, **kwds):
        logger.debug('[WRAP] <%s>', func.__name__)
        # utime.sleep(0.5)
        response = func(obj, *args, **kwds)
        if response:
            logger.debug('[WRAP] <%s>: Success', func.__name__)
        else:
            logger.error('[WRAP] <%s>: Failed', func.__name__)
        # utime.sleep(0.5)
        return response

    return wrapper


# 【decorator】 プロパティ値の read/write : DEBUGレベル
def propfunc(func):
    def wrapper(obj, *args, **kwds):
        logger.debug('[WRAP] <%s>: [%s]', func.__name__, args)
        response = func(obj, *args, **kwds)
        logger.debug('[WRAP] <%s>: [%s]', func.__name__, response)
        # utime.sleep(0.5)
        return response

    return wrapper


# 【calc】 [y, m, d] の曜日を求める 0 = 日曜日　｛未使用｝
def day_of_week(y, m, d):
    t = (0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4)
    if m < 3:
        y -= 1
    return (y + y // 4 - y // 100 + y // 400 + t[m - 1] + d) % 7


# 【calc】 [y, m, d] が、1月1日から何日目かを求める
def days_of_year(y, m, d):
    t = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    if m > 2 and (y % 4 == 0) and (y % 100 == 0 or y % 400 != 0):
        d += 1
    return sum(t[:m - 1]) + d


# 【calc】 [yyyy-mm-dd hh:mm:ss] -> [year, month, day, hour, minute, second]
def strftime(tm, *, fmt='{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}'):
    (year, month, day, hour, minute, second) = tm[:6]
    return fmt.format(year, month, day, hour, minute, second)


# 【calc】 直近の検針日 collect_date からの経過日数を求める
def days_after_collect(collect_date):
    (year, month, today) = utime.localtime()[:3]        # 今日の日付 today を求める
    days1 = days_of_year(year, month, today)            # days1 1月1日からの経過日数
    if today < collect_date[month]:                     # 今日が今月の検針日より前なら
        day = collect_date[month - 1]                   #     起点は前月の検針日
        if month == 1:                                  #     検針日より前かつ1月なら
            return 31 - day + today                     #         検針日からの経過日数を返す
        else:                                           #     検針日より前で1月以外なら
            days2 = days_of_year(year, month - 1, day)  #         前月検針日の経過日数
    else:                                               # 今日が今月の検針日以後なら
        day = collect_date[month]                       #     起点は当月の検針日
        days2 = days_of_year(year, month, day)          #     今月検針日の経過日数
    return days1 - days2                                # [今日 - 直近検針日] を返す


# 【calc】 直近の検針日を求める
def last_collect_day(collect_date):
    (year, month, today) = utime.localtime()[:3]  # 今日の日付 today を求める
    if today < collect_date[month]:               # 今日が今月の検針日より前なら
        day = collect_date[month - 1]               #     起点は前月の検針日
        if month == 1:                            #     （検針日より前かつ）1月なら
            year -= 1                             #         直近検針日は前年
            month = 12                            #         直近検針日は12月
        else:                                     #     （検針日より前）かつ1月以外なら
            month -= 1                            #         直近検針日は前月
    else:                                         # 今日が今月の検針日以後なら
        day = collect_date[month]                 #     起点は当月の検針日
    return strftime((year, month, day, 0, 0, 0))  # 直近の検針日を返す


# クラス BP35A1
class BP35A1:

    def __init__(self,
                 id,
                 password,
                 collect_date,
                 ipv6_addr,
                 coefficient,
                 unit,
                 *,
                 progress_func=None,
                 log_level=None
                 ):

        self.uart = machine.UART(1, tx=0, rx=26)
        self.uart.init(115200, bits=8, parity=None, stop=1, timeout=2000)

        self.id = id
        self.password = password
        self.collect_date = collect_date
        self.ipv6_addr = ipv6_addr
        self.coefficient = coefficient
        self.unit = unit
        self.progress = progress_func if progress_func else lambda _: None

        self.scan = {}  # 'Channel', 'Pan ID', 'Addr', 'LQI'

        global logger
        log_level = getattr(logging, log_level, None)
        logging.basicConfig(level=log_level)
        logger = logging.getLogger('BP35A1')
        logger.info('[INIT] Class BP35A1 imported')


# 【初期化　セクション】

    # 【init】 uart をフラッシュ
    def flash(self):
        utime.sleep(0.5)
        while self.uart.any():
            _ = self.uart.read()
        self.uart.write('\r\n')
        utime.sleep(0.5)

    # 【init】 スキャンデータをリセット
    def reset_scan(self):
        for file_name in uos.listdir('/flash'):
            if file_name == 'smm_scan.json':
                uos.remove('/flash/smm_scan.json')

        self.scan = {}
        self.ipv6_addr = None
        self.coefficient = None
        self.unit = None

    # 【init】 BP53A1の初期化　'SKRESET' と 'SKSREG SFE 0'
    @skfunc
    def skInit(self):
        return (self.exec_command('SKRESET') and self.exec_command('SKSREG SFE 0'))

    # 【init】 ROPT で ERXUDPデータ表示形式を確認して、バイナリモードならASCIIモードに変更
    @iofunc
    def set_WOPT(self):
        self.writeln('ROPT')
        utime.sleep(0.5)
        mode_flg = False
        while True:
            ln = self.readln()
            if ln.decode().startswith('OK 01'):
                logger.info('[INIT] BP35A1 = [ASCII Mode]')
                break
            elif ln.decode().startswith('OK 00'):
                logger.info('[INIT] BP35A1 = [Binary Mode]')
                mode_flg = True
                break
            utime.sleep(0.5)

        if mode_flg:
            self.writeln('WOPT 01')
            logger.info('[INIT] Setting [ASCII Mode]')
            utime.sleep(0.5)
            while True:    # Echo back & OK wait!
                ln = self.readln()
                if ln.decode().startswith('OK'):
                    logger.info('[INIT] Set [ASCII Mode] OK')
                    break

    # 【init】 SKSTACK IP のファームウェアバージョンを表示 ※未使用
    @skfunc
    def skVer(self):
        return self.exec_command('SKVER')

    # 【init】 以前のPANAセッション解除
    @skfunc
    def skTerm(self):
        return self.exec_command('SKTERM')

    # 【init】 Bルート認証：パスワード セット
    @skfunc
    def skSetPasswd(self):
        return self.exec_command('SKSETPWD C ', self.password)

    # 【init】 Bルート認証：ID セット
    @skfunc
    def skSetID(self):
        return self.exec_command('SKSETRBID ', self.id)

    # 【init】 smm_scan.json があれば読み込む
    @skfunc
    def smm_scan_filechk(self):
        scanfile_flg = False
        for file_name in uos.listdir('/flash'):
            if file_name == 'smm_scan.json':
                scanfile_flg = True
        if scanfile_flg:
            logger.info('[INIT] <smm_scan.json> found')
            with open('/flash/smm_scan.json') as f:
                d = ujson.load(f)
                self.scan = d

            # 各要素の文字数でデータチェック
            if (len(str(self.scan.get('Channel'))) == 2
                and len(str(self.scan.get('Pan ID'))) == 4
                and len(str(self.scan.get('Addr'))) == 16
                and len(str(self.scan.get('LQI'))) == 2
                ):

                scanfile_flg = True

            else:
                logger.info('[INIT] <smm_scan.json> Illegal')
                scanfile_flg = False

        else:
            logger.info('[INIT] <smm_scan.json> not found')
        return scanfile_flg

    # 【init】 アクティブスキャン実行　：　結果を smm_scan.json に書き出す
    @skfunc
    def skScan(self, duration=4):
        while duration <= 7:
            self.reset_scan()
            self.writeln('SKSCAN 2 FFFFFFFF ' + str(duration))

            self.scan = {}  # 必要か？？

            while True:
                ln = self.readln()
                if ln.startswith('EVENT 22'):
                    break

                if ':' in ln:
                    key, val = ln.decode().strip().split(':')[:2]
                    self.scan[key] = val

            # 各要素の文字数でデータチェック
            if (len(str(self.scan.get('Channel'))) == 2
                and len(str(self.scan.get('Pan ID'))) == 4
                and len(str(self.scan.get('Addr'))) == 16
                and len(str(self.scan.get('LQI'))) == 2
                ):

                with open('/flash/smm_scan.json', 'w') as f:
                    ujson.dump(self.scan, f)
                    logger.info('[INIT] <smm_scan.json> saved')

                logger.info('[INIT] Active Scan : Success')
                return True

            duration = duration + 1

        return False

    # 【init】 IPV6アドレスの取得
    @skfunc
    def skLL64(self):
        self.writeln('SKLL64 ' + self.scan['Addr'])
        while True:
            ln = self.readln()
            val = ln.decode().strip()
            if val:
                self.ipv6_addr = val
                return True

    # 【init】 無線CH設定
    @skfunc
    def skSetChannel(self):
        return self.exec_command('SKSREG S2 ', self.scan['Channel'])

    # 【init】 受信PAN-IDの設定
    @skfunc
    def skSetPanID(self):
        return self.exec_command('SKSREG S3 ', self.scan['Pan ID'])

    # 【init】 スマートメーターに接続
    @skfunc
    def skJoin(self):
        self.writeln('SKJOIN ' + self.ipv6_addr)
        while True:
            ln = self.readln()
            if ln.startswith('EVENT 24'):
                return False
            elif ln.startswith('EVENT 25'):
                return True

    # 【init】 ping : 指定した IPv6 アドレス宛てに ICMP Echo request を送信
    @skfunc
    def skPing(self):

        retries = 0

        while retries <= 5:  # リトライ回数
            try:
                self.writeln('SKPING ' + self.ipv6_addr)
                ln = self.readln()
                val = ln.decode().strip()
                if val.startswith('OK'):
                    ln = self.readln()
                    val = ln.decode().strip()
                    if val.startswith('EPONG'):
                        return True
                
                retries += 1
                
            except Exception as e:
                logger.error('[SYS_] %s [retries = %d]', e, retries)
                retries += 1

        raise Exception('BP35A1.skPing() retry over.')


# 【I/O セクション】

    # 【I/O】 UART データ読込み
    @iofunc
    def readln(self, timeout=TIMEOUT_20s):
        s = utime.time()
        while (utime.time() - s) < timeout:
            if self.uart.any() != 0:
                return self.uart.readline()
        raise Exception('== Timeout BP35A1.readln() : ' + str(timeout) + ' seconds ==', )

    # 【I/O】 UART データ書き込み
    @iofunc
    def write(self, data):
        self.uart.write(data)

    # 【I/O】 UART データ書き込み
    @iofunc
    def writeln(self, data):
        self.uart.write(data + '\r\n')

    # 【I/O】 コマンドの送信
    def exec_command(self, cmd, arg=''):
        self.writeln(cmd + arg)
        return self.wait_for_ok()

    # 【I/O】 'OK' が返ってきたら True、　’FAIL' が返ってきたら False
    def wait_for_ok(self):
        while True:
            if self.uart.any() != 0:
                ln = self.readln()
                if ln.decode().startswith('OK'):
                    return True
                elif ln.decode().startswith('FAIL'):
                    return False


# 【プロパティ セクション】

    # 【property】 プロパティ値を読み書きの実行
    @skfunc
    def skSendTo(self, data):
        self.write('SKSENDTO 1 {0} 0E1A 1 {1:04X} '.format(self.ipv6_addr, len(data)))
        self.write(data)
        return True

    # 【property】 プロパティ値読み出し
    @propfunc
    def read_property(self, epc, timeout=TIMEOUT_20s):
        self.skSendTo((
            b'\x10\x81'  # EHD
            b'\x00\x01'  # TID
            b'\x05\xFF\x01'  # SEOJ
            b'\x02\x88\x01'  # DEOJ 低圧スマート電力量メータークラス
            b'\x62'  # ESV プロパティ値読み出し(62)
            b'\x01'  # OPC 1個
        ) + bytes([int(epc, 16)]) + (
            b'\x00'  # PDC Read
        ))

        return self.wait_for_data(timeout)
    
    # 【property】 プロパティ値読み出し（瞬時電力＋瞬時電流)
    @propfunc
    def read_property_wa(self, timeout=TIMEOUT_20s):
        self.skSendTo((
            b'\x10\x81'  # EHD
            b'\x00\x01'  # TID
            b'\x05\xFF\x01'  # SEOJ
            b'\x02\x88\x01'  # DEOJ 低圧スマート電力量メータークラス
            b'\x62'  # ESV プロパティ値読み出し(62)
            b'\x02'  # OPC 2個
            b'\xE7\x00\xE8\x00'  # E7(瞬時電力) & E8(瞬時電流)
        ))

        return self.wait_for_data(timeout)

    # 【property】 プロパティ値書き込み
    @propfunc
    def write_property(self, epc, value, timeout=TIMEOUT_20s):
        self.skSendTo((
            b'\x10\x81'  # EHD
            b'\x00\x01'  # TID
            b'\x05\xFF\x01'  # SEOJ
            b'\x02\x88\x01'  # DEOJ 低圧スマート電力量メータークラス
            b'\x61'  # ESV プロパティ値書き込み(61)
            b'\x01'  # OPC 1個
        ) + bytes([int(epc, 16)]) + (
            b'\x01'  # PDC Write
        ) + bytes([value]))

        return self.wait_for_data(timeout)


# 【データ取得　セクション】

    # 【get_data】 積算電力量-履歴データ(E2)の取得 n日前
    def get_hist_cumul_e_energy(self, n):

        retries = 0

        while retries <= 3:  # リトライ回数
            try:
                # 積算電力量-履歴データ-収集日(E5)の設定
                utime.sleep(1)
                self.write_property('E5', n)
                # 積算電力量-履歴データ(E2)の取得
                utime.sleep(1)
                (days, history_of_e_energy) = self.read_property('E2', TIMEOUT_60s)
                # 定時積算電力量計測値(EA)の取得
                utime.sleep(1)
                (created, e_energy) = self.read_property('EA')

                return created, history_of_e_energy

            except Exception as e:
                logger.error('[HIST] %s [retries = %d]', e, retries)
                retries += 1

        raise Exception('BP35A1.get_hist_cumul_e_energy() retry over.')

    # 【get_data】 定時積算電力量計測値(EA)の取得
    def get_cumul_e_energy(self):
        utime.sleep(1)
        return self.read_property('EA')

    # 【get_data】 瞬時電力計測値(E7)の取得
    def get_instantaneous_wattage(self):
        utime.sleep(1)
        return self.read_property('E7')

    # 【get_data】 瞬時電流計測値(E8)の取得
    def get_instantaneous_amperage(self):
        utime.sleep(1)
        return self.read_property('E8')

    # 【get_data】 瞬時電力計測値(E7) & 瞬時電流計測値(E8)の取得
    def get_instantaneous_data(self):
        utime.sleep(1)
        return self.read_property_wa()


    # 【get_data】　前回検針日を起点とした積算電力量計測値履歴１(E2)の取得
    def get_monthly_e_energy(self):

        retries = 0

        while retries <= 3:  # リトライ回数
            try:
                # 積算履歴収集日１(E5)の設定
                utime.sleep(1)
                self.write_property('E5', days_after_collect(self.collect_date))
                # 積算電力量計測値履歴１(E2)の取得
                utime.sleep(1)
                (days, collected_e_energy) = self.read_property('E2', TIMEOUT_60s)
                (days, collected_e_energy) = (days, int(collected_e_energy[0:0 + 8], 16)
                                              * self.coefficient * self.unit)
                # 定時積算電力量計測値(EA)の取得
                utime.sleep(1)
                (created, e_energy) = self.read_property('EA')

                # 前回検針日と定時積算電力量計測値(EA)との差分
                monthly_e_energy = e_energy - collected_e_energy

                return (last_collect_day(self.collect_date), monthly_e_energy, created, e_energy)
            except Exception as e:
                logger.error('[CUML] %s [retries = %d]', e, retries)
                retries += 1

        raise Exception('BP35A1.get_monthly_e_energy() retry over.')


# 【メイン　セクション】

    # 【main】 スマートメーターに接続
    def open(self):

        # バッファをクリア
        self.progress(0)
        self.flash()

        # BP53A1の初期化　'SKRESET' と 'SKSREG SFE 0' を実行
        self.progress(10)
        if not self.skInit():
            return False

        # ERXUDPデータ表示形式がバイナリモードならASCIIモードへ変更
        self.progress(20)
        self.set_WOPT()

        # 以前のPANAセッション解除 : 通常は解除するセッションが無いので、エラー'ER10' が返ってくる
        self.skTerm()

        # Bルート認証IDの設定
        self.progress(30)
        if not (self.skSetPasswd() and self.skSetID()):
            return False

        while True:
            try:
                # スマートメーターのスキャン
                self.progress(40)
                if self.smm_scan_filechk() is False:
                    logger.info('[INIT] Exec Active Scan')
                    if not self.skScan():  # アクティブスキャン実行
                        continue
                else:
                    logger.info('[INIT] Skip Active Scan')

                # IPV6アドレスの取得
                self.progress(50)
                if not self.skLL64():
                    continue

                # 無線CH設定、受信PAN-IDの設定
                self.progress(60)
                if not (self.skSetChannel() and self.skSetPanID()):
                    continue

                # スマートメーターに接続
                self.progress(70)
                if not self.skJoin():
                    self.reset_scan()  # スキャン結果をリセット
                    continue

                # 係数(D3)の取得 coefficient
                self.progress(80)
                if self.coefficient is None:
                    self.coefficient = self.read_property('D3')
                logger.info('[INIT] coefficient = %s', str(self.coefficient))
                utime.sleep(1)

                # 積算電力量単位(E1)の取得 unit
                self.progress(90)
                if self.unit is None:
                    self.unit = self.read_property('E1')
                logger.info('[INIT] unit = %s', str(self.unit))
                utime.sleep(1)

                # 処理ループ終了 return
                self.progress(100)
                return (self.scan['Channel'],
                        self.scan['Pan ID'],
                        self.scan['Addr'],
                        self.scan['LQI'],
                        self.ipv6_addr,
                        self.coefficient,
                        self.unit)

            except Exception as e:
                logger.error(e)

    # 【main】 データ取得_メイン
    def wait_for_data(self, timeout=TIMEOUT_20s):
        start = ut = utime.time()
        while ut - start < timeout:
            if self.uart.any() != 0:
                ln = self.readln(timeout)
                if not ln.decode().startswith('ERXUDP'):
                    continue

                values = ln.decode().strip().split(' ')
                if not len(values) == 9:
                    continue

                data = values[8]
                seoj = data[8:8 + 6]
                esv = data[20:20 + 2]
                epc = data[24:24 + 2]

                # 低圧スマート電力量メータ(028801)
                if seoj != '028801':
                    continue

                # 積算電力量係数(D3) : coefficient
                if esv == '72' and epc == 'D3':
                    coefficient = int(data[-8:], 16)
                    return coefficient

                # 積算電力量単位(E1) : unit
                if esv == '72' and epc == 'E1':
                    unit = {
                        '00': 1.0,
                        '01': 0.1,
                        '02': 0.01,
                        '03': 0.001,
                        '04': 0.0001,
                        '0A': 10.0,
                        '0B': 100.0,
                        '0C': 1000.0,
                        '0D': 10000.0,
                    }[data[-2:]]
                    return unit

                # 積算電力量-履歴データ(E2) : hist_cumul_e_energy
                if esv == '72' and epc == 'E2':
                    days = int(data[30:30 + 2], 16)
                    e_energy = data[32:32 + 8 * 48]
                    return days, e_energy

                # 積算電力量-履歴データ-収集日(E5)
                if esv == '71' and epc == 'E5':
                    result = int(data[-2:], 16)
                    return result

                # 瞬時電力計測値(E7) : instantaneous_wattage
                if esv == '72' and epc == 'E7' and len(data) == 36:
                    wattage = int(data[-8:], 16)
                    return strftime(utime.localtime()), wattage

                # 瞬時電流計測値(E8) : instantaneous_amperage
                if esv == '72' and epc == 'E8' and len(data) == 36:
                    amperage_r = int(data[-8:-8 + 4], 16)
                    if amperage_r == 0x7ffe:
                        amperage_r = 0
                    amperage_t = int(data[-4:], 16)
                    if amperage_t == 0x7ffe:
                        amperage_t = 0
                    return strftime(utime.localtime()), (amperage_r + amperage_t) / 10.0

                # 瞬時電力計測値(E7) & 電流計測値(E8): instantaneous_wattage & amperage
                if esv == '72' and epc == 'E7' and len(data) == 48:
                    wattage = int(data[-20:-12], 16)
                    amperage_r = int(data[-8:-8 + 4], 16)
                    if amperage_r == 0x7ffe:
                        amperage_r = 0
                    amperage_t = int(data[-4:], 16)
                    if amperage_t == 0x7ffe:
                        amperage_t = 0
                    return wattage, (amperage_r + amperage_t) / 10.0

                # 定時積算電力量(EA) : cumul_e_energy
                if esv == '72' and epc == 'EA':
                    (year, month, day, hour, minute, second) = (
                        int(data[-22:-22 + 4], 16),
                        int(data[-18:-18 + 2], 16),
                        int(data[-16:-16 + 2], 16),
                        int(data[-14:-14 + 2], 16),
                        int(data[-12:-12 + 2], 16),
                        int(data[-10:-10 + 2], 16)
                    )
                    created = strftime(
                        (year, month, day, hour, minute, second))
                    e_energy = (int(data[-8:], 16) * self.coefficient * self.unit)

                    return created, e_energy

            ut = utime.time()

        raise Exception('== Timeout BP35A1.wait_for_data : ' + str(timeout) + ' seconds ==', )

    # 【main】　スマートメーターとの接続解除
    def close(self):
        self.skTerm()


# 動作確認用ルーチン
if __name__ == '__main__':
    id = 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'  # Bルート ID
    password = 'xxxxxxxxxxxx'                # Bルート パスワード
    contract_amperage = "40"
    collect_cal = [1] * 13
    ipv6_addr = None
    coefficient = None
    unit = None

    bp35a1 = BP35A1(id, password, collect_cal, ipv6_addr, coefficient, unit)
    bp35a1.open()

    for i in range(10):
        try:
            (datetime, data) = bp35a1.get_instantaneous_wattage()
            print('Instantaneous wattage {} {}W'.format(datetime, data))

            (datetime, data) = bp35a1.get_cumul_e_energy()
            print('Cumulative e energy {} {}kWh'.format(datetime, data))

        except Exception as e:
            logger.error(e)

    bp35a1.close()
