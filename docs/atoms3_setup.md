# ATOM S3 セットアップ（CircuitPythonの書き込みから）

`smm3_sub_atoms3.py`（子機、ATOM S3用）を動かすには、まずATOM S3本体にCircuitPython自体を
書き込む必要があります。本体README「4. ファイル構成」はCircuitPythonが**既に書き込み済み**の
前提で書かれているため、ここでは白紙の（購入したままの）ATOM S3に書き込むところから説明します。

既にCircuitPythonが動いている個体をお持ちの場合は、この手順は不要です。本体READMEの
「4. ファイル構成」の ATOM S3 ブロックへ進んでください。

## 対応バージョンについて

**CircuitPython 9.2.9系での動作を確認しています。10系（10.2.1で確認）は動作不良が出たため、
現時点では非推奨です**（具体的な不具合の症状は未記録のため、詳細を知りたい場合はご自身で
10系を試して報告いただけると助かります）。9.2.9より新しい9.x系（9.2.10等）は未検証ですが、
迷ったら9.2.9を使うのが無難です。

## 必要なもの

- `esptool`（`pip3 install esptool`でインストール）
- TinyUF2ブートローダー：[github.com/adafruit/tinyuf2 の Releases](https://github.com/adafruit/tinyuf2/releases)
  から、ボード名 `m5stack_atoms3` 向けの `tinyuf2-m5stack_atoms3-*-combined.bin` をダウンロード
- CircuitPython本体：[circuitpython.org/board/m5stack_atoms3](https://circuitpython.org/board/m5stack_atoms3/)
  から、バージョン **9.2.9** の `.uf2` ファイルをダウンロード（言語はen_US推奨、日本語版でも動作に
  差はないはず）

## 手順

### 1. TinyUF2ブートローダーを書き込む

ATOM S3をUSB接続し、シリアルポート名を確認します。

```bash
ls /dev/cu.*
```

`/dev/cu.usbmodemXXXXXXXXXXXX` のような名前が対象デバイスです。それを指定して書き込みます
（`XXXXXXXXXXXX`部分は実際のポート名に置き換えてください）。

```bash
esptool.py --chip esp32s3 --port /dev/cu.usbmodemXXXXXXXXXXXX --baud 460800 write_flash 0x0 tinyuf2-m5stack_atoms3-0.35.0-combined.bin
```

書き込み完了後、**USBケーブルを一度抜き差し**してください。ATOM S3がTinyUF2ブートローダーで
起動し、`ATOMS3BOOT` という名前のUSBドライブとしてマウントされます。

### 2. CircuitPython本体を書き込む

ダウンロードした `.uf2` ファイルを `ATOMS3BOOT` ドライブへコピーします。

```bash
cp adafruit-circuitpython-m5stack_atoms3-en_US-9.2.9.uf2 /Volumes/ATOMS3BOOT/
```

コピーの最後に `Input/output error` が出ることがありますが、これは書き込み成功後に
デバイス側が自分でアンマウントするために起きる**正常な動作**です。慌てず次へ進んでください。

もう一度**USBケーブルを抜き差し**すると、今度は `CIRCUITPY` という名前のドライブと、新しい
シリアルポートが現れます。

### 3. 書き込み内容を確認する

`CIRCUITPY` ドライブ直下の `boot_out.txt` を開き、以下が表示されていることを確認します。

```
Adafruit CircuitPython 9.2.9 on ...
Board ID:m5stack_atoms3
```

ここまででCircuitPython自体のセットアップは完了です。

## SMM3のコードを書き込む

ここから先は、本体README「4. ファイル構成」のATOM S3ブロックと同じ内容です。

1. `circup` をインストール（未インストールなら）：`pip3 install circup`
2. ライブラリをインストール：`circup install adafruit_display_text adafruit_bitmap_font adafruit_ticks`
3. `smm3_sub_atoms3.py` を `/Volumes/CIRCUITPY/code.py` としてコピー
4. `fonts/` 内の必須3ファイル（`DSEG7Classic-Bold-32.bdf` / `Arial-Bold-18.bdf` / `Arial-Bold-12.bdf`）を
   `/Volumes/CIRCUITPY/fonts/` へコピー（詳しくは [../fonts/README.md](../fonts/README.md)）
5. `smm3_sub_atoms3.settings.toml.template` を元に `/Volumes/CIRCUITPY/settings.toml` を作成
   （空ファイルでも可）
6. シリアルコンソールに接続し、`Ctrl-D` を押すとソフトリブートして `code.py` が実行されます。
   画面に表示が出れば成功です。

## トラブルシューティング

- **画面が表示されない／起動が不安定**：CircuitPythonのバージョンを確認してください。10系を
  使っている場合は9.2.9系へ書き直してみてください（上記手順で `.uf2` を入れ替えるだけで、
  ブートローダーの再書き込みは不要です）。
- **`Input/output error`が怖くて止まってしまう**：上記「2. CircuitPython本体を書き込む」の通り、
  書き込み成功後の正常な挙動です。抜き差し後に`CIRCUITPY`ドライブが現れているか確認してください。
