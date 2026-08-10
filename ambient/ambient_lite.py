# ambient.py（AmbientDataInc/ambient-python-lib, MIT License）の軽量版。
# 元ライブラリのうち、このプロジェクトが使うsend()のみ・MicroPython経路のみに絞り、
# read()/getprop()/putcmnt()/sethide()と非micro(CPython requests)分岐を削除。
#
# 既知のバグ修正: 元のsend()はurequests.post()にtimeoutを渡していたが、実機FWのurequestsは
# timeout=非対応（TypeError）。さらにurequests自体、無応答時に無限に近くブロックする
# （2026-08-08、ambidata.io停止時に実機で18〜19秒のハングを確認）。
# 本体側の_web_post()と同じ手法（生ソケット+settimeout）に置き換え、無応答を確実にタイムアウト化する。
import usocket
import utime

AMBIENT_POST_TIMEOUT = 15  # 秒。無応答時はこの時間で例外化する（本体_web_postのWEB_POST_TIMEOUTと同じ考え方）


class Ambient:
    def __init__(self, channelId, writeKey):
        self.channelId = channelId
        self.writeKey = writeKey
        self.host = 'ambidata.io'
        self.path = '/api/v2/channels/' + str(channelId) + '/dataarray'
        self.lastsend = 0

    def send(self, data, timeout=AMBIENT_POST_TIMEOUT):
        millis = utime.ticks_ms()
        if self.lastsend != 0 and utime.ticks_diff(millis, self.lastsend) < 4999:
            return False  # 連投防止（元ライブラリのstatus_code=403相当）

        d = data if isinstance(data, list) else [data]
        import ujson
        body = ujson.dumps({'writeKey': self.writeKey, 'data': d})

        ai = usocket.getaddrinfo(self.host, 80)[0][-1]
        so = usocket.socket()
        so.settimeout(timeout)
        try:
            so.connect(ai)
            req = ('POST ' + self.path + ' HTTP/1.0\r\n'
                   + 'Host: ' + self.host + '\r\n'
                   + 'Content-Type: application/json\r\n'
                   + 'Content-Length: ' + str(len(body)) + '\r\n'
                   + 'Connection: close\r\n\r\n' + body)
            so.write(req.encode())
            so.read(32)  # 応答の頭を読む＝無応答はsettimeoutで例外化（本体_web_postと同じ確認方法）
            self.lastsend = utime.ticks_ms()
            return True
        finally:
            try:
                so.close()
            except Exception:
                pass
