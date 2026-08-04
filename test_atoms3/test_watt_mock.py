"""
ワット表示モック（微調整用）
smm3_sub_atoms3.py の MODE_SIMPLE 瞬時電力表示部分だけを切り出して
固定値"8888"で表示する。値はここでは更新しない（位置・サイズ調整専用）。
"""

import board
import displayio
from adafruit_display_text import label
from adafruit_bitmap_font import bitmap_font

BG_COLOR      = 0x102030
COLOR_MID     = 0x1F77B4
COLOR_UNCOLOR = 0xA0A0A0   # M5Stack版 uncolor（"W"単位文字）

WATT_BOTTOM_Y = 54    # 瞬時電力値の下端y
WATT_RIGHT_X  = 109   # 瞬時電力値の右端x

display = board.DISPLAY
font_dseg7_main = bitmap_font.load_font("/fonts/DSEG7Classic-Bold-32.bdf")
font_arial_b12 = bitmap_font.load_font("/fonts/Arial-Bold-12.bdf")

bg_bmp = displayio.Bitmap(128, 128, 1)
bg_pal = displayio.Palette(1)
bg_pal[0] = BG_COLOR
g = displayio.Group()
g.append(displayio.TileGrid(bg_bmp, pixel_shader=bg_pal))

g0_watt = label.Label(font_dseg7_main, text="8888", color=COLOR_MID)
g0_watt.anchor_point = (1.0, 1.0)
g0_watt.anchored_position = (WATT_RIGHT_X, WATT_BOTTOM_Y)
g.append(g0_watt)

g0_w = label.Label(font_arial_b12, text="W", color=COLOR_UNCOLOR)
g0_w.anchor_point = (1.0, 1.0)
g0_w.anchored_position = (126, WATT_BOTTOM_Y)
g.append(g0_w)

display.root_group = g

while True:
    pass
