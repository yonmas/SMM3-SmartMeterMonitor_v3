# フォントファイル配置先

ATOM S3を初期化（CIRCUITPYをフォーマット/再フラッシュ）した際は、このフォルダの
`.bdf` ファイルを CIRCUITPY の `/fonts/` にコピーすること。

```
cp fonts/DSEG7Classic-Bold-32.bdf /Volumes/CIRCUITPY/fonts/DSEG7Classic-Bold-32.bdf
cp fonts/Arial-Bold-18.bdf /Volumes/CIRCUITPY/fonts/Arial-Bold-18.bdf
cp fonts/Arial-Bold-12.bdf /Volumes/CIRCUITPY/fonts/Arial-Bold-12.bdf
```

`smm3_sub_atoms3.py` が `bitmap_font.load_font("/fonts/DSEG7Classic-Bold-32.bdf")`
（MODE_SIMPLE/MODE_TODAY共通のwatt表示）、`"/fonts/Arial-Bold-18.bdf"`
（累積電力量・料金の数値）、`"/fonts/Arial-Bold-12.bdf"`（計算期間・kWh/Yen単位、"W"単位）
で読み込む。これらが無いと起動時に `OSError: [Errno 2] No such file/directory` で停止する。

`DSEG7Classic-Bold-40.bdf` は `test_atoms3/test_display_watt_simple.py`（別スクリプト）が
使用するため `fonts/` 直下に残してある。

## fonts/unused/ について

本番（`smm3_sub_atoms3.py`）からも `test_atoms3/` のスクリプトからも読み込まれなくなった
フォントの置き場所。

- `DSEG7Classic-Bold-36.bdf`: 旧MODE_TODAY専用サイズ。MODE_TODAYのwatt表示を
  MODE_SIMPLEと同じ32px(`DSEG7Classic-Bold-32.bdf`)に統一したため不要になった
- `Junction-Regular-24.bdf`: サンセリフ体比較で試した候補。`test_font_compare.py`の
  比較対象からも外れ、どこからも参照されていない
- `LeagueSpartan-Bold-16.bdf` / `Arial-16.bdf`: 同じく比較候補。本番では不採用だが、
  `test_atoms3/test_font_compare.py`は`/fonts/LeagueSpartan-Bold-16.bdf`等のデバイス側
  フラットパスで今も読み込む。実機で試す際は`fonts/unused/`から
  `/Volumes/CIRCUITPY/fonts/`へ直接コピーすること

## DSEG7Classic-Bold-*.bdf の生成方法

CircuitPythonの `adafruit_bitmap_font` は BDF/PCF 形式のみ対応（TTF不可）。
DSEG7（7セグメント風）フォントの公式配布はTTF/WOFFのみなので、`otf2bdf` で
各ピクセルサイズのBDFに変換した。

1. DSEG7フォントのTTFを入手（例: `DSEG7Classic-Bold.ttf`、
   https://github.com/keshikan/DSEG ）
2. `otf2bdf` をインストール（macOS: `brew install otf2bdf`）
3. 以下を実行（`-r 72` でDPIを72にすることで `-p` のポイント数=ピクセル数になる）

```
otf2bdf -p 40 -r 72 -o DSEG7Classic-Bold-40.bdf DSEG7Classic-Bold.ttf
otf2bdf -p 32 -r 72 -o DSEG7Classic-Bold-32.bdf DSEG7Classic-Bold.ttf
```

使用文字は数字0-9・`-`・`.`のみなので、これらのグリフが含まれていればOK。

## Arial-Bold-18.bdf / Arial-Bold-12.bdf について

累積電力量・料金の数値表示（Arial-Bold-18）と、計算期間・kWh/Yen単位表示
（Arial-Bold-12）に使用。DSEG7（7セグメント風）ではなく通常のサンセリフ体の方が
視認性・見映えが良いため採用。いずれもAdafruit CircuitPython Bundle の
`examples/pyoa/cyoa_titano/fonts/Arial_Bold_18.bdf` /
`examples/pyoa/cave/fonts/Arial_Bold_12.bdf` をそのまま使用（変換不要）。
Arial-Bold-12: PIXEL_SIZE=12、ASCENT=15・DESCENT=3。Arial-Bold-18: PIXEL_SIZE=18、
ASCENT=22・DESCENT=5。

`LeagueSpartan-Bold-16.bdf`（OFL） / `Arial-16.bdf`（MIT、Regular16px） /
`Junction-Regular-24.bdf`（OFL）はサイズ・太さ比較のために試した候補。
最終的にArial Boldを採用し、`fonts/unused/`に移動した（前者2つは
`test_atoms3/test_font_compare.py`での再比較用に内容は保持してある）。

## ライセンス

DSEG7フォント（変換元）は SIL Open Font License 1.1（Reserved Font Name "DSEG"）。
[DSEG-LICENSE.txt](DSEG-LICENSE.txt) を同梱。

League Spartan・JunctionもSIL Open Font License 1.1（各Reserved Font Name付き）。
それぞれの`.bdf.license`ファイルを同梱。

Arial（Arial-16.bdf・Arial-Bold-12.bdf・Arial-Bold-18.bdf）はAdafruitがCircuitPython Bundleの
examplesで「SPDX-License-Identifier: MIT」を付けて配布しているものをそのまま使用。
Arial自体はMonotype社の商用フォントなので、**このBDF以外のサイズ・太さを
Macの`/System/Library/Fonts/Supplemental/Arial.ttf`等から自前で生成して
配布・commitするのは不可**（Adafruit配布のexamples内の既存BDFのみ利用可）。

OFLは改変（フォーマット変換含む）・再配布・商用利用を許可しているため、
このリポジトリでの保存・配布は問題ない。ただし以下条件を守ること。

- フォント単体での販売は不可（成果物への組み込み・同梱は可）
- フォントファイルを取り出せる形で配布する場合、著作権表示または
  ライセンスファイルの同梱が必要（embedして取り出せない形なら不要）
- 「DSEG」「League Spartan」「Junction」という名称を、無関係の改変フォントに
  無断で使うのは不可（今回はDSEG7はフォーマット変換のみ、League Spartan・Junctionは
  無改変そのままなので問題なし）
