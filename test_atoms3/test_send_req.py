"""
ESP-NOW送信APIテスト
"""

import os, time, wifi, espnow

ssid     = os.getenv("WIFI_SSID")
password = os.getenv("WIFI_PASSWORD")

if ssid:
    try:
        wifi.radio.connect(ssid, password)
        print("WiFi OK")
    except Exception as ex:
        print(f"WiFi NG: {ex}")
        wifi.radio.enabled = True
else:
    wifi.radio.enabled = True

e     = espnow.ESPNow()
bcast = espnow.Peer(mac=b"\xff\xff\xff\xff\xff\xff", encrypted=False)
e.peers.append(bcast)
print(f"peers: {list(e.peers)}")

# --- パターン1: e.send(message, peer) ---
print("[1] e.send(b'REQ00', bcast)  ", end="")
try:
    r = e.send(b"REQ00", bcast)
    print(f"-> {r}")
except Exception as ex:
    print(f"-> ERROR: {ex}")

time.sleep(1)

# --- パターン2: e.send(peer, message) ---
print("[2] e.send(bcast, b'REQ00')  ", end="")
try:
    r = e.send(bcast, b"REQ00")
    print(f"-> {r}")
except Exception as ex:
    print(f"-> ERROR: {ex}")

time.sleep(1)

# --- 受信待機（5秒）---
print("--- 受信待機 ---")
t = time.monotonic()
while time.monotonic() - t < 5:
    pkt = e.read()
    if pkt:
        raw = pkt.msg
        print(f"RX({len(raw)}B): key={raw[2:6]}")
    time.sleep(0.05)

print("done")
