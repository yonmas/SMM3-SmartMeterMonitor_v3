// SMM3 Dashboard - GAS Web App
// 親機からの M:CUML / M:INST 相当のデータを受け取って表示する。
// このコードの正本はリポジトリ側（SMM3/gas_dashboard/）。エディタで直接編集すると
// 次の clasp push で上書きされるため、修正はリポジトリ側で行うこと。

var PROP = PropertiesService.getScriptProperties();

// ---- 状態監視(無音検知)設定 ----
var STALE_SEC = 600;    // この秒数データが途絶えたら「異常(stale)」＝フリーズ/再起動連発/オフラインの疑い
                        // inst=30秒毎/cuml=10分毎なので、単発の再起動(~2-3分)では誤検知しない値
var ALERT_EMAIL = '';   // 通知先メール。空ならメール送信せずダッシュボード表示のみ。
                        // Script Propertiesの 'alertEmail' でも上書き可（コード変更不要）
var DEFAULT_WARN_AMP = 30;  // 警告アンペアの初期値。設定用GSSの WARNING_AMPERAGE と同じ既定値だが、
                            // 以降はダッシュボードの設定ページで独立して変更する（シートとは同期しない）

function doGet(e) {
  if (e.parameter.action === 'data') {
    return ContentService.createTextOutput(JSON.stringify(getDashboardData()))
      .setMimeType(ContentService.MimeType.JSON);
  }
  // 設定の保存。既存の action=data と同じGETの流儀に揃える（Netlifyのiframe越しでも確実に通る）。
  // URLを知っていれば誰でも変更できるが、変えられて困る値が無いため認証は設けていない。
  if (e.parameter.action === 'saveSettings') {
    return ContentService.createTextOutput(JSON.stringify(saveSettings(e.parameter)))
      .setMimeType(ContentService.MimeType.JSON);
  }
  if (e.parameter.action === 'testMail') {
    return ContentService.createTextOutput(JSON.stringify(sendTestMail()))
      .setMimeType(ContentService.MimeType.JSON);
  }
  var tmpl = HtmlService.createTemplateFromFile('Dashboard');
  tmpl.data = getDashboardData();
  tmpl.execUrl = ScriptApp.getService().getUrl();
  return tmpl.evaluate()
    .setTitle('SMM3 Dashboard')
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
  } else if (body.type === 'cuml') {
    PROP.setProperty('cuml', JSON.stringify(body));
    appendHistory(body.created, body.e_energy);
  } else if (body.type === 'backfill') {
    backfillHistory(body.points);
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
// 警告アンペアとメール通知はGAS内で完結。契約アンペアだけは親機がcumlで送ってくる値の表示専用。
function getSettings() {
  var warn = parseFloat(PROP.getProperty('warnAmp'));
  var contract = parseFloat(PROP.getProperty('contractAmp'));
  var lastCheck = PROP.getProperty('lastCheckAt');
  return {
    warnAmp: isNaN(warn) ? DEFAULT_WARN_AMP : warn,
    contractAmp: isNaN(contract) ? null : contract,
    // 通知のON/OFFは別フラグを持たず「アドレスが空かどうか」だけで表す（設定項目を二重にしない）
    alertEmail: PROP.getProperty('alertEmail') || ALERT_EMAIL || '',
    triggerInstalled: PROP.getProperty('triggerInstalled') === '1',
    triggerError: PROP.getProperty('triggerError') || null,
    lastCheckAt: lastCheck || null
  };
}

// 通知の実体である「5分毎の時間トリガー」を、通知先アドレスの有無に合わせて自動で設置/削除する。
// これによりユーザーの操作は「アドレスを入れる＝ON / 空にする＝OFF」だけで完結する。
// ScriptApp が権限不足で落ちる可能性があるため必ず try/catch で囲み、失敗しても
// saveSettings 全体（ひいてはダッシュボード）を巻き込まないようにする。失敗の内容は
// triggerError に残し、設定ページで手動設置を案内する材料にする。
function syncHealthTrigger(email) {
  try {
    var existing = ScriptApp.getProjectTriggers().filter(function (t) {
      return t.getHandlerFunction() === 'checkHealth';
    });
    if (email) {
      if (existing.length === 0) {
        ScriptApp.newTrigger('checkHealth').timeBased().everyMinutes(5).create();
      }
      PROP.setProperty('triggerInstalled', '1');
    } else {
      existing.forEach(function (t) { ScriptApp.deleteTrigger(t); });
      PROP.deleteProperty('triggerInstalled');
      PROP.deleteProperty('lastCheckAt');   // 次にONにした時、古い打刻を生存と誤認しないよう消す
    }
    PROP.deleteProperty('triggerError');
  } catch (e) {
    PROP.setProperty('triggerError', String((e && e.message) || e));
  }
}

// 送られてきたパラメータのうち、指定されたものだけ更新する（未指定の項目は現状維持）
function saveSettings(p) {
  if (p.warnAmp !== undefined && p.warnAmp !== '') {
    var w = parseFloat(p.warnAmp);
    if (!isNaN(w) && w > 0) PROP.setProperty('warnAmp', String(w));
  }
  if (p.alertEmail !== undefined) {
    var email = String(p.alertEmail).trim();
    var before = PROP.getProperty('alertEmail') || '';
    PROP.setProperty('alertEmail', email);
    // 空⇔非空が変わった時だけトリガーを触る（毎回ScriptAppを叩かない）
    if (!!email !== !!before) syncHealthTrigger(email);
  }
  return getSettings();
}

// 設定ページの「テスト送信」。通知先が正しいかを、親機が実際に止まるのを待たずに確かめる。
// MailAppが権限エラーを投げてもこの分岐の中で握り潰し、他のaction（特にaction=data）に
// 波及させない。ダッシュボード全体を落とさないことを最優先する。
function sendTestMail() {
  var email = PROP.getProperty('alertEmail') || ALERT_EMAIL;
  if (!email) {
    return { ok: false, error: '通知先アドレスが未設定です' };
  }
  try {
    MailApp.sendEmail(email, '[SMM3] テスト送信',
      'SMM3ダッシュボードからのテストメールです。\n' +
      'このメールが届いていれば、通知先の設定は正しく行われています。\n\n' +
      '実際の通知は、親機からのデータが' + STALE_SEC + '秒以上途絶えたときに送られます。');
    return { ok: true, to: email };
  } catch (e) {
    return { ok: false, error: '送信に失敗しました: ' + e.message };
  }
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

// 時間トリガ(installHealthTriggerで5分毎に設置)から呼ばれる。状態が変化した時だけ通知。
// 監視のみ＝検知して知らせるだけ。再起動などの復旧アクションは一切しない。
function checkHealth() {
  // トリガーが生きている証跡。設定ページの「監視トリガーの状態」はこの鮮度だけで判定する
  // （ScriptApp.getProjectTriggers()は匿名アクセスから呼べないため。getSettings()のコメント参照）
  PROP.setProperty('lastCheckAt', new Date().toISOString());

  var h = getHealth(new Date());
  var prev = PROP.getProperty('alertState') || 'ok';
  // アドレスが空＝通知OFF。空でもalertStateの遷移だけは記録する
  // （アドレスを設定した直後に、過去の異常で誤発報しないため）
  var email = PROP.getProperty('alertEmail') || ALERT_EMAIL;

  if (h.status === 'stale' && prev !== 'stale') {
    if (email) {
      MailApp.sendEmail(email, '[SMM3] 親機データ未着（異常）',
        '親機からのデータが約' + h.ageSec + '秒途絶えています（閾値' + h.thresholdSec + '秒）。\n' +
        '最終受信: ' + h.lastSeenAt + ' / 種別: ' + h.lastType);
    }
    PROP.setProperty('alertState', 'stale');
  } else if (h.status === 'ok' && prev === 'stale') {
    if (email) {
      MailApp.sendEmail(email, '[SMM3] 親機データ復帰',
        'データ受信が復帰しました。最終受信: ' + h.lastSeenAt);
    }
    PROP.setProperty('alertState', 'ok');
  }
}

// 手動設置用のフォールバック。通常は通知先アドレスを入れた時に syncHealthTrigger() が
// 自動で設置するので実行不要。自動設置が権限等で失敗した場合にエディタから一度だけ実行する。
// （重複回避のため既存のcheckHealthトリガは削除してから作り直す）
function installHealthTrigger() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'checkHealth') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('checkHealth').timeBased().everyMinutes(5).create();
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
