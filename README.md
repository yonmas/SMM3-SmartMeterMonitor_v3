# SMM3 : Smart Meter Monitor v.3

## お知らせ（2024/05/07）
電気料金の計算関数に、電気料金プランを追加しました。設定用Googleスプレッドシート（設定用GSS）の **電気料金計算関数名** に、関数名を入力して設定用GSSの再読込み、もしくは再起動をしてください。設定用GSSの料金単価設定方法は、[calc_charge.py] を参照してください。（ご希望の料金プラン関数があれば、リクエストいただければ対応します。）

**東京電力：**
- tepco : 従量電灯B
- tepco_smartlife_s : スマートライフS

**中部電力：** ※祝祭日料金には対応していません。
- chubu_smartlife : スマートライフプラン（スタンダード）
- chubu_smartlife_asa : スマートライフプラン（朝とく）
- chubu_smartlife_yoru : スマートライフプラン（夜とく）

仕様変更により、起動後に電気料金が表示されるまで、数分間の時間がかかるようになりました。

履歴データ読込み時のインジケーター（赤点滅）がうまく表示されなかったのを修正しました。

設定用GSSの、**燃料費調整額** と **再エネ賦課金** の項目位置（上下）を入れ替えました。

タイマーリソース不足により挙動が不安定なため、子機の checkWiFi() の定期実行を中止しました。
(2024/05/07)

---
**M5Stackで電力使用量を「見える化」して電気代を節約しよう！**

[![title](https://github-production-user-asset-6210df.s3.amazonaws.com/104808539/273613295-9f8fb870-071d-44b1-a14b-477ec1338b59.jpg)](https://www.youtube.com/watch?v=5jaRR_evKWo)

## 0. 最低限の手順

**「[細かいこと](https://docs.google.com/spreadsheets/d/1qYsY8ZOpj6FxqoebCQnvBFYSL8rCK7r_A7R3m9bF7MY/edit#gid=158599453)」** はいいから、とりあえず使ってみたいという場合は、以下の手順で。

1. M5Stack Basic/Core2 と M5StickC Plus を準備して、M5StickC Plus に BP35A1 を組み込んでください。**[2.使用機器]** 参照。
1. **[4.ファイル構成]** に従って、必要なファイルを 親機：M5StickC、子機：M5Stack にインストールしてください。  
1. **[5.初期設定]** に従って、機器の初期設定を行ってください。

## 1. 概要

親機：M5StickC Plus + Wi-SUNモジュール BP35A1 で、家庭のスマートメーターから電力使用量のデータを取得して、子機：M5Stackの画面ににいろいろ表示します。前日、直近7日間、直近30日間の電力使用量との比較をグラフ化。眺めていると、ついつい節電したくなるはずです。

### 以前のバージョンからの変更点：

- ページのオートローテーション機能を追加
- 直近30日間のデータ表示を追加
- 直近7日間のグラフに日付を追加
- Bルートアカウント他、主要な設定のGoogleスプレッドシートからの読込みに対応
- 表示の見直し、内部処理の効率化、その他

### ページ構成（手動およびオートローテーション）：

1. 瞬時電力 (W)／瞬時電流 (A)／検針日からの積算電力量 (kWh)／検針日からの電気料金 (円)
1. 30分ごとの使用電力量グラフ（当日／前日）
1. 1時間毎の使用電力量内訳表（当日／前日）
1. 現時点まで／終日の電力使用量グラフ（当日／直近7日間）
1. 1時間毎の使用電力量内訳表（当日／直近7日間）
1. 現時点まで／終日の電力使用量グラフ（当日／直近30日間）
1. 1時間毎の使用電力量内訳表（当日／直近30日間）

システム全体は、 @rin-ofumi さんの記事をベースにしています。Wi-SUN HAT の作者さんです。  
<https://kitto-yakudatsu.com/archives/7206>  
子機のシステムは、 @rin-ofumi さんのコードをベースにしています。  
<https://github.com/rin-ofumi/m5stickc_wisun_hat>  
親機のシステムと全体の表示形式は、 @miyaichi さんのコードをベースにしています。  
<https://github.com/miyaichi/SmartMeter>

（子機：M5Stack Basic/Core2 のファームは、**V1.10.2** 以降としてください。）

## 2. 使用機器

- 親機：M5StickC Plus --> [スイッチサイエンス](https://www.switch-science.com/products/6470/)
- 子機：M5Stack Basic --> [スイッチサイエンス](https://www.switch-science.com/products/9010/)  
- 子機：M5Stack Core2 --> [スイッチサイエンス](https://www.switch-science.com/products/9349/)  
- BP35A1 モジュール --> [チップワンストップ](https://www.chip1stop.com/view/searchResult/SearchResultTop?classCd=&did=&cid=netcompo&keyword=BP35A1&utm_source=netcompo&utm_medium=buyNow)
- Wi-SUN HAT --> [スイッチサイエンス](https://www.switch-science.com/products/7612/)

※ M5Stick および M5Stack を電源に繋いで長期運用する場合は、バッテリーを撤去した方が安心かもしれません。  
※ 親機だけでも動きますが、子機を追加することで、より多様なデータ表示が実現できます。  
※ 複数子機の運用に対応しています。

## 3. 事前準備

電力会社にBルートサービスの利用開始を申し込み、認証IDとパスワードを取得する。  
--> [東京電力申込みサイト](https://www.tepco.co.jp/pg/consignment/liberalization/smartmeter-broute.html)

Ambient でアカウントを作成し、チャネルを作成。チャネルIDとライトキーを取得する。  
（オプション：取得した電力や使用量をクラウド上に記録、グラフ化するサービス（無料）です。）  
--> [Ambient](https://ambidata.io/)

## 4. ファイル構成

```text
■■ 親機（main)：M5StickC Plus + Wi-SUN HAT(with BP35A1 module) ■■

/apps/
  +- smm3_main.py (親機メインプログラム)

/（ルート）
  +- bp35a1.py (BP35A1クラス)
  +- func_main.py (外部モジュール)
  +- calc_charge.py (電気料金計算モジュール)
  +- logging.py (別途準備)
  +- ambient.py (オプション：別途準備)
  ===== 以下のファイルはGSSによる設定を行わない場合のみ使用 =====
  +- api_config.json (オプション：設定用GoogleスプレッドシートのAPI情報)
  +- config_main.json (オプション：親機設定ファイル)
```

```text
■■ 子機(sub)：M5Stack Basic/Core2 ■■ 
※ Basic用とCore2用、それぞれ専用のプログラムを使用してください。
※ M5Stack Basic のファームは、V1.10.2 以降としてください。

/apps/
  +- smm3_sub.py (子機メインプログラム　※Basic用)
  +- smm3_sub_core2.py (子機メインプログラム　※Core2用)

/（ルート）
  +- func_sub.py (外部モジュール　※Basic用)
  +- func_sub_core2.py (外部モジュール　※Core2用)
  +- logging.py (別途準備)
  ===== 以下のファイルはGSSによる設定を行わない場合のみ使用 =====
  +- api_config.json (オプション：設定用GoogleスプレッドシートのAPI情報)
  +- config_sub.json (オプション：子機設定ファイル)
```
同梱の _config_main.json, _api_config.json は、必要最低限の設定値（それぞれ、Bルートのアカウント、設定用Googleスプレッドシート（設定用GSS）のAPI情報）のみを記載したものです。アンダーバーを削除してお使いください。記載のない設定値はプログラム内の初期値が使用されます。（添付の設定用ファイルの各項目の値とプログラム内の初期値は同じです。）

#### モジュールのダウンロードはこちらから

[ambient.py](https://github.com/AmbientDataInc/ambient-python-lib/blob/master/ambient.py)  
[logging.py](https://github.com/m5stack/M5Stack_MicroPython/blob/master/MicroPython_BUILD/components/micropython/esp32/modules/logging.py)

## 5. 初期設定

Step-1. [設定用Googleスプレッドシート（設定用GSS）の準備とGoogle Sheets APIの取得（SMM_config）](https://docs.google.com/spreadsheets/d/1qYsY8ZOpj6FxqoebCQnvBFYSL8rCK7r_A7R3m9bF7MY/edit#gid=2004069989)  
Step-2. [設定用GSSのAPI設定読み込み（SMM_API_config）](https://docs.google.com/spreadsheets/d/1MmbDpG4GTfwRiHsFgsJ89XaIqkVF537lReL4glnOHuc/edit#gid=276533579)  
　※ それぞれリンク先の説明を参照してください。

## 6. ボタンの説明

### 親機

* Aボタン　　　：上下反転
* Aボタン長押し：設定用GSSから設定読込み
* Bボタン長押し：履歴データ再取得 (new!)

### 子機

* Aボタン　　　：ページ進む
* Bボタン　　　：ページ戻る
* Cボタン　　　：アンペア警告音 on/off
* Aボタン長押し：設定用GSSから設定読込み
* Bボタン長押し：オートローテーション on/off
* Cボタン長押し：履歴データ再取得

## その他

**[GoogleスプレッドシートのReademe](https://docs.google.com/spreadsheets/d/1qYsY8ZOpj6FxqoebCQnvBFYSL8rCK7r_A7R3m9bF7MY/edit#gid=158599453)** に、もう少し細かい情報を書き記しているので、参考にしてください。

## お知らせ履歴
M5Stack Core2 に対応する子機用プログラムを追加しました。Basic用とCore2用、それぞれ使用機器に合わせてインストールしてください。

Wi-Fi接続確認のルーチンが作動していなかったのを修正しました。他、細かいバグを修正しました。

設定用Googleスプレッドシート（設定用GSS）の構成を変更しました。最新版のプログラムと設定用GSSの組み合わせで利用してください。BasicとCore2で、画面の明るさ設定項目が異なるので注意してください。
(2024/04/10)

---
子機のグラフ表示に使う履歴データをスマートメータから取得するロジックを根本的に見直しました。また、内部処理に挿入していたウェイトを、動作に影響がないと思われる範囲で削減。結果として、初期化時にかかる時間を大幅に短縮しました。

【見直し前】子機からのリクエストに応じて、その都度、親機がスマートメーターから履歴データを取得・転送していました。  
【見直し後】親機の起動時にスマートメーターから履歴データを取得して、親機内に保存、随時更新。子機からのリクエスには、親機内に保存している履歴データを送信するようにしました。  

親機の履歴データを再取得するため、[Bボタン長押し] を追加しました。その際には、自動的に子機の履歴データも更新されます。
(2023/10/21)

---
一部の設定用変数名を変更しました。最新のコードと設定用GSSをご利用ください！！(2023/10/10)
