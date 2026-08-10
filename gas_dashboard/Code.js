// SMM3 Dashboard - GAS Web App
// 親機からの M:CUML / M:INST 相当のデータを受け取って表示する。
// このコードの正本はリポジトリ側（SMM3/gas_dashboard/）。エディタで直接編集すると
// 次の clasp push で上書きされるため、修正はリポジトリ側で行うこと。

var PROP = PropertiesService.getScriptProperties();

// ---- サンプル公開デプロイ用ガード ----
// 「smm3-sample」として恒久公開するデプロイのIDをここに固定する。クエリパラメータ等の
// クライアント指定値ではなく、Google側が発行するデプロイURL自体（ScriptApp.getService().getUrl()）
// で判定するため、URLからパラメータを外しても実データ（PROP/Historyシート、本番と共有）には
// 一切到達できない。本番デプロイはこのIDと一致しないので影響を受けない。
var SAMPLE_DEPLOYMENT_ID = 'AKfycbyh1aHjcnLZEFN9zbYsMYU3y1akYv9cBDS8DMpXAEoK8TSCm-pTlugXkCiTltrDiQeS';
function isSampleDeployment() {
  return ScriptApp.getService().getUrl().indexOf(SAMPLE_DEPLOYMENT_ID) !== -1;
}

// ---- 一時共有デプロイ(smm3-share-003e7a3f)用ガード ----
// 知人への一時公開用。数値・週/月等は実データのまま見せるが、瞬時グラフ(InstLog)だけは
// 詳細な生活パターンが読み取れてしまうため、サンプルと同じくテストデータに固定する。
// 判定方法はサンプルと同じくデプロイURL自体（クエリでは変更不可）。
var TEMP_SHARE_DEPLOYMENT_ID = 'AKfycbyE0jD9aImaDTjGrvQ8hOl-VSUqqGMWWJsRBajXCMYovdC4nuSFFlugsWcjZjjqTQzm';
function isTempShareDeployment() {
  return ScriptApp.getService().getUrl().indexOf(TEMP_SHARE_DEPLOYMENT_ID) !== -1;
}

// ---- 状態監視(無音検知)設定 ----
var STALE_SEC = 600;    // この秒数データが途絶えたら「異常(stale)」＝フリーズ/再起動連発/オフラインの疑い
                        // inst=30秒毎/cuml=10分毎なので、単発の再起動(~2-3分)では誤検知しない値
                        // 異常の通知はダッシュボードの赤画面＋バナーで行う（メール通知は持たない。
                        // 匿名Webアプリからは MailApp/ScriptApp が権限エラーになり、承認作業を
                        // 全利用者に強いる割に、画面表示以上の価値が無いため 2026-08-05 に撤去）
var DEFAULT_WARN_AMP = 30;  // 警告アンペアの初期値。設定用GSSの WARNING_AMPERAGE と同じ既定値だが、
                            // 以降はダッシュボードの設定ページで独立して変更する（シートとは同期しない）

function doGet(e) {
  // サンプル公開デプロイかどうかは常にデプロイURL自体で判定（クエリでは変えられない、上記参照）
  var sample = isSampleDeployment();

  if (e.parameter.action === 'data') {
    return ContentService.createTextOutput(JSON.stringify(sample ? SAMPLE_SNAPSHOT : getDashboardData()))
      .setMimeType(ContentService.MimeType.JSON);
  }
  // InstLogグラフ用。source=test は負荷テスト専用のInstLogTestシート（20160行の合成データ、
  // seedTestInstLog()で生成）、それ以外は本番InstLogの実データ。サンプルデプロイ／一時共有
  // デプロイでは、クエリのsource指定に関わらず常にテストデータを返す（実データへは到達させない）。
  // tail=N を付けると末尾N行だけ（＝初期表示の高速化用）、無指定なら全件を返す
  if (e.parameter.action === 'instlog') {
    var tail = e.parameter.tail ? parseInt(e.parameter.tail, 10) : null;
    var useTest = sample || isTempShareDeployment() || e.parameter.source === 'test';
    var result = useTest ? readInstLogTestRows(tail) : readInstLogRows(tail);
    return ContentService.createTextOutput(JSON.stringify(result))
      .setMimeType(ContentService.MimeType.JSON);
  }
  // 設定の保存。既存の action=data と同じGETの流儀に揃える（Netlifyのiframe越しでも確実に通る）。
  // URLを知っていれば誰でも変更できるが、変えられて困る値が無いため認証は設けていない。
  // サンプルデプロイでは保存ボタン自体をUI側で非表示にしているが、直叩き対策として
  // ここでも何もせず現在の（固定）設定を返すだけにする。
  if (e.parameter.action === 'saveSettings') {
    return ContentService.createTextOutput(JSON.stringify(sample ? SAMPLE_SNAPSHOT.settings : saveSettings(e.parameter)))
      .setMimeType(ContentService.MimeType.JSON);
  }
  var tmpl = HtmlService.createTemplateFromFile('Dashboard');
  tmpl.data = sample ? SAMPLE_SNAPSHOT : getDashboardData();
  tmpl.execUrl = ScriptApp.getService().getUrl();
  tmpl.isSample = sample;
  return tmpl.evaluate()
    .setTitle(sample ? 'SMM3 Dashboard (Sample)' : 'SMM3 Dashboard')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

function doPost(e) {
  var body = JSON.parse(e.postData.contents);
  // 全メッセージ共通の最終受信時刻（無音検知の基準）。inst停止でもcuml等が来ていれば生存とみなせる
  PROP.setProperty('lastSeenAt', new Date().toISOString());
  PROP.setProperty('lastType', String(body.type || '?'));
  if (body.type === 'inst') {
    PROP.setProperty('current', JSON.stringify({
      watt: body.watt,
      amp: body.amp,
      muted: !!body.muted,
      updatedAt: new Date().toISOString()
    }));
    appendInstLog(body.watt, body.amp);
  } else if (body.type === 'cuml') {
    PROP.setProperty('cuml', JSON.stringify(body));
    appendHistory(body.created, body.e_energy);
  } else if (body.type === 'backfill') {
    backfillHistory(body.created, body.e_energy);
  } else if (body.type === 'boot') {
    recordBoot(body.cause);
  } else if (body.type === 'config') {
    // 親機が起動時に1回だけ送ってくる設定値。今は契約アンペアのみで、正本は設定用GSS。
    // ここでは設定ページに表示するためにキャッシュするだけ（GAS側からは変更しない）。
    // 何年も変わらない値なので再送は無く、次の再起動まで前回の値を保持し続ける。
    if (body.contract !== undefined && body.contract !== null && body.contract !== '') {
      PROP.setProperty('contractAmp', String(body.contract));
    }
  }
  return ContentService.createTextOutput('OK');
}

// 親機起動時の 'boot' 報告を記録。累積再起動回数＋直近ログ（時刻/原因）を恒久保存し頻度把握に使う。
// 電力データ（current/cuml/History）とは別枠。RTCが本機で再起動を跨がないためGAS側が記録の本体。
function recordBoot(cause) {
  var cnt = parseInt(PROP.getProperty('rebootCount') || '0', 10) + 1;
  PROP.setProperty('rebootCount', String(cnt));
  var log = JSON.parse(PROP.getProperty('rebootLog') || '[]');
  var now = new Date();
  var prev = log.length ? new Date(log[log.length - 1].at) : null;
  var gapMin = prev ? Math.round((now.getTime() - prev.getTime()) / 60000) : null;
  log.push({ n: cnt, at: now.toISOString(), cause: cause, gapMin: gapMin });  // gapMin=前回起動からの経過分
  if (log.length > 100) log = log.slice(log.length - 100);   // 直近100件ローリング（即時表示用）
  PROP.setProperty('rebootLog', JSON.stringify(log));
  // 恒久記録：Reboots シートへ日時付きで1行追記（best-effort、シート障害でboot記録自体は壊さない）。
  // at はJST表記にする（now.toISOString()はUTCで21:25→12:25とズレるため明示的にAsia/Tokyoへ整形）。
  // ※PROPのlog(上のat)はISO(UTC)のまま：gapMin計算とダッシュボードのfmtTime(ブラウザでJST変換)に使うため。
  try {
    appendReboot(Utilities.formatDate(now, 'Asia/Tokyo', 'yyyy-MM-dd HH:mm:ss'), cause, cnt, gapMin);
  } catch (e) {}
}

// ---- 設定（PropertiesService保存＝家族全員で共通の1組。誰が変えても全員に反映される） ----
// 警告アンペアはGAS内で完結。契約アンペアは親機がconfigで送ってくる値の表示専用。
function getSettings() {
  var warn = parseFloat(PROP.getProperty('warnAmp'));
  var contract = parseFloat(PROP.getProperty('contractAmp'));
  return {
    warnAmp: isNaN(warn) ? DEFAULT_WARN_AMP : warn,
    contractAmp: isNaN(contract) ? null : contract
  };
}

// 送られてきたパラメータのうち、指定されたものだけ更新する（未指定の項目は現状維持）
function saveSettings(p) {
  if (p.warnAmp !== undefined && p.warnAmp !== '') {
    var w = parseFloat(p.warnAmp);
    if (!isNaN(w) && w > 0) PROP.setProperty('warnAmp', String(w));
  }
  return getSettings();
}

function getDashboardData() {
  var current = JSON.parse(PROP.getProperty('current') || 'null');
  var cuml = JSON.parse(PROP.getProperty('cuml') || 'null');
  var rows = readHistoryRows();
  var now = new Date();

  var today, week, month, todayHourly, yesterdayHourly, weekAvgHourly, monthAvgHourly;

  if (rows.length > 0) {
    today = realToday(rows, now);
    week = realWeek(rows, now);
    month = realMonth(rows, now);
    todayHourly = toHourly(today.today);
    yesterdayHourly = toHourly(today.yesterday);
    weekAvgHourly = avgHourlyProfile(rows, now, 7);
    monthAvgHourly = avgHourlyProfile(rows, now, 30);
  } else {
    // 蓄積データがまだ無い間は、偽の値ではなく素直に空（未取得）として返す
    today = { today: new Array(48).fill(null), yesterday: new Array(48).fill(null) };
    week = { today: null, days: new Array(7).fill({ date: '-', sub: null, total: null }), avgSub: null, avgTotal: null };
    month = { today: null, days: new Array(30).fill({ date: '-', sub: null, total: null }), avgSub: null, avgTotal: null };
    todayHourly = new Array(24).fill(null);
    yesterdayHourly = new Array(24).fill(null);
    weekAvgHourly = new Array(24).fill(null);
    monthAvgHourly = new Array(24).fill(null);
  }

  return {
    current: current,
    cuml: cuml,
    today: today,
    week: week,
    month: month,
    tables: {
      ytdy: buildTable(todayHourly, yesterdayHourly),
      avg7: buildTable(todayHourly, weekAvgHourly),
      avg30: buildTable(todayHourly, monthAvgHourly)
    },
    health: getHealth(now),
    settings: getSettings(),
    reboot: {
      count: parseInt(PROP.getProperty('rebootCount') || '0', 10),
      log: JSON.parse(PROP.getProperty('rebootLog') || '[]')
    }
  };
}

// ---- 状態監視：最終受信からの経過で健全性を返す（表示・通知の共通判定） ----
function getHealth(now) {
  now = now || new Date();
  var iso = PROP.getProperty('lastSeenAt');
  if (!iso) {
    return { status: 'unknown', lastSeenAt: null, ageSec: null, lastType: null, thresholdSec: STALE_SEC };
  }
  var ageSec = Math.round((now.getTime() - new Date(iso).getTime()) / 1000);
  return {
    status: ageSec > STALE_SEC ? 'stale' : 'ok',
    lastSeenAt: iso,
    ageSec: ageSec,
    lastType: PROP.getProperty('lastType') || null,
    thresholdSec: STALE_SEC
  };
}

// 30分×48スロット → 1時間×24（smm3_sub_core2.pyのdraw_table相当の集計単位に合わせる）
function toHourly(slots48) {
  var hourly = [];
  for (var h = 0; h < 24; h++) {
    var a = slots48[h * 2], b = slots48[h * 2 + 1];
    hourly.push((a == null || b == null) ? null : round2(a + b));
  }
  return hourly;
}

// smm3_sub_core2.py の draw_table() と同じ突き合わせ：時間毎の今日・比較対象・差分、当日合計・比較合計・比率
function buildTable(todayHourly, avgHourly) {
  var rows = [];
  var totalToday = 0, totalAvg = 0;
  for (var h = 0; h < 24; h++) {
    var t = todayHourly[h], a = avgHourly[h];
    // 当日(t)が0は「まだ計測されていない（未来の時間帯）」場合と区別できないため、
    // 子機が"---"でごまかしているのと同じ理由で、その時間帯の差は表示しない(null)
    var diff = (t == null || t === 0 || !a) ? null : round2(t - a);
    rows.push({ hour: h, today: t, avg: a, diff: diff });
    if (t != null) totalToday += t;
    if (a) totalAvg += a;
  }
  var ratio = totalAvg > 0 ? Math.round((totalToday / totalAvg) * 100) : null;
  return { rows: rows, totalToday: round2(totalToday), totalAvg: round2(totalAvg), ratio: ratio };
}

function round2(v) {
  return Math.round(v * 100) / 100;
}
