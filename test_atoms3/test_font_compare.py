"""
サンセリフ体フォント比較サンプル
累積電力量・料金表示用フォントの候補を並べて表示する。
"""

import board
import displayio
import terminalio
from adafruit_display_text import label
from adafruit_bitmap_font import bitmap_font

BG_COLOR = 0x102030
LABEL_COLOR = 0x778899
VALUE_COLOR = 0xE08040

display = board.DISPLAY

bg_bmp = displayio.Bitmap(128, 128, 1)
bg_pal = displayio.Palette(1)
bg_pal[0] = BG_COLOR
g = displayio.Group()
g.append(displayio.TileGrid(bg_bmp, pixel_shader=bg_pal))

candidates = [
    ("1 LeagueSpartan Bold16", "/fonts/LeagueSpartan-Bold-16.bdf"),
    ("2 Arial Regular16",      "/fonts/Arial-16.bdf"),
    ("3 Arial Bold18",         "/fonts/Arial-Bold-18.bdf"),
]

ROW_Y = (2, 34, 70)   # 各フォントの実高さ(19/23/32px)に合わせた行位置

for (name, path), y0 in zip(candidates, ROW_Y):
    name_lbl = label.Label(terminalio.FONT, text=name, color=LABEL_COLOR)
    name_lbl.anchor_point = (0.0, 0.0)
    name_lbl.anchored_position = (2, y0)
    g.append(name_lbl)

    font = bitmap_font.load_font(path)
    sample_lbl = label.Label(font, text="3004", color=VALUE_COLOR)
    sample_lbl.anchor_point = (0.0, 0.0)
    sample_lbl.anchored_position = (2, y0 + 10)
    g.append(sample_lbl)

display.root_group = g

while True:
    pass
