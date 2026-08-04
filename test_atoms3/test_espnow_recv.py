"""
ESP-NOW最小受信テスト - CircuitPython on ATOM S3
目的: MicroPython親機のブロードキャストを受信できるか確認する
"""

import os
import time
import wifi
import espnow

print("ESP-NOW受信テスト")
print("================")

# WiFi接続（親機と同じチャンネルに乗るために必要）
ssid = os.getenv("WIFI_SSID")
password = os.getenv("WIFI_PASSWORD")

if ssid:
    print(f"WiFi接続: {ssid}")
    try:
        wifi.radio.connect(ssid, password)
        ch = wifi.radio.ap_info.channel if wifi.radio.ap_info else "?"
        print(f"接続OK ch={ch}")
    except Exception as ex:
        print(f"WiFi失敗: {ex}")
        print("ラジオのみで続行")
        wifi.radio.enabled = True
else:
    wifi.radio.enabled = True
    print("WiFI_SSID未設定")
    print("settings.tomlを確認")

mac = ":".join(f"{b:02x}" for b in wifi.radio.mac_address)
print(f"MAC: {mac}")
print("----------------")

# ESP-NOW初期化
e = espnow.ESPNow()

# ブロードキャストをピアに登録（これがないとブロードキャスト受信不可）
bcast = espnow.Peer(mac=b"\xff\xff\xff\xff\xff\xff", encrypted=False)
e.peers.append(bcast)

print("受信待機中...")
count = 0

while True:
    packet = e.read()
    if packet is not None:
        count += 1
        try:
            msg = packet.msg.decode("utf-8")
            if msg.startswith("M:"):
                key = msg[2:6]
                body = msg[6:]
                print(f"[{count}] key={key} body={body[:30]}")
            else:
                print(f"[{count}] (M:なし) {msg[:30]}")
        except Exception:
            print(f"[{count}] raw: {packet.msg[:16]}")
    time.sleep(0.05)
