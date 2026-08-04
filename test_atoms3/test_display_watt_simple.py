"""
SMM3 ATOM - 瞬時電力・画面中央表示（シンプル版）
CircuitPython on ATOM S3 (128×128)

数字を画面中央にドンと表示するだけのシンプルバージョン。
→ smm3_sub_atoms3.py（グラフ付き）とのボタン切り替えを後で統合予定。
"""

import os
import time
import struct
import wifi
import espnow
import board
import busio
import displayio
import terminalio
from adafruit_display_text import label
from adafruit_bitmap_font import bitmap_font

# ---- カラー定義 ----
BG_COLOR = 0x102030
COLOR_LOW  = 0x00DD88
COLOR_MID  = 0x00AAFF
COLOR_HIGH = 0xFF8800
COLOR_WARN = 0xFF2020
COLOR_UNIT = 0x445566
COLOR_AMP  = 0x556677

WARNING_AMPERAGE = 30


def watt_color(w, a):
    if a >= WARNING_AMPERAGE:
        return COLOR_WARN
    if w < 500:
        return COLOR_LOW
    if w < 2000:
        return COLOR_MID
    if w < 3000:
        return COLOR_HIGH
    return COLOR_WARN


# ---- IMU (MPU6886) ----
_MPU_ADDR   = 0x68
_PWR_MGMT_1 = 0x6B
_ACCEL_XOUT = 0x3B

try:
    _i2c = busio.I2C(scl=board.IMU_SCL, sda=board.IMU_SDA)
except AttributeError:
    _i2c = board.I2C()

while not _i2c.try_lock():
    pass
_i2c.writeto(_MPU_ADDR, bytes([_PWR_MGMT_1, 0x00]))
_i2c.unlock()


def read_accel():
    while not _i2c.try_lock():
        pass
    _i2c.writeto(_MPU_ADDR, bytes([_ACCEL_XOUT]))
    buf = bytearray(6)
    _i2c.readfrom_into(_MPU_ADDR, buf)
    _i2c.unlock()
    ax, ay, az = struct.unpack(">hhh", buf)
    return ax / 16384.0, ay / 16384.0, az / 16384.0


def accel_to_rotation(ax, ay):
    if abs(ax) > abs(ay):
        return 270 if ax > 0 else 90
    return 0 if ay < 0 else 180


# ---- ディスプレイ ----
display    = board.DISPLAY
font_dseg7 = bitmap_font.load_font("/fonts/DSEG7Classic-Bold-40.bdf")

group = displayio.Group()

# 背景
_bg_bmp = displayio.Bitmap(128, 128, 1)
_bg_pal = displayio.Palette(1)
_bg_pal[0] = BG_COLOR
group.append(displayio.TileGrid(_bg_bmp, pixel_shader=_bg_pal))

# 瞬時電力値（画面中央）
watt_lbl = label.Label(font_dseg7, text="---", color=COLOR_MID)
watt_lbl.anchor_point = (0.5, 0.5)
watt_lbl.anchored_position = (64, 64)
group.append(watt_lbl)

# "W" 単位（右下）
w_lbl = label.Label(terminalio.FONT, text="W", color=COLOR_UNIT, scale=2)
w_lbl.anchor_point = (1.0, 1.0)
w_lbl.anchored_position = (126, 126)
group.append(w_lbl)

# 電流値（左下）
amp_lbl = label.Label(terminalio.FONT, text="", color=COLOR_AMP, scale=1)
amp_lbl.anchor_point = (0.0, 1.0)
amp_lbl.anchored_position = (2, 126)
group.append(amp_lbl)

display.root_group = group

# ---- WiFi & ESP-NOW ----
ssid     = os.getenv("WIFI_SSID")
password = os.getenv("WIFI_PASSWORD")

if ssid:
    try:
        wifi.radio.connect(ssid, password)
    except Exception:
        wifi.radio.enabled = True
else:
    wifi.radio.enabled = True

e = espnow.ESPNow()
e.peers.append(espnow.Peer(mac=b"\xff\xff\xff\xff\xff\xff", encrypted=False))

# ---- メインループ ----
wattage     = 0
amperage    = 0.0
current_rot = display.rotation
rot_t       = time.monotonic()

while True:
    packet = e.read()
    if packet is not None:
        try:
            msg = packet.msg.decode("utf-8")
            if msg.startswith("M:INST"):
                w, a    = msg[6:].split("/")
                wattage  = int(w)
                amperage = float(a)
                watt_lbl.color = watt_color(wattage, amperage)
                watt_lbl.text  = str(wattage)
                amp_lbl.text   = f"{amperage:.1f} A"
        except Exception:
            pass

    now = time.monotonic()
    if now - rot_t >= 0.5:
        rot_t = now
        try:
            ax, ay, _ = read_accel()
            new_rot = accel_to_rotation(ax, ay)
            if new_rot != current_rot:
                display.rotation = new_rot
                current_rot = new_rot
        except Exception:
            pass

    time.sleep(0.05)
