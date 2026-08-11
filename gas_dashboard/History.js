// GAS側の履歴蓄積・集計ロジック。
// type:'cuml' を受信するたびに [created, e_energy] をSheetへ1行追記し、
// today/week/month/時間別表は、その蓄積データから都度計算する。

var HISTORY_SHEET_NAME = 'History';
var REBOOT_SHEET_NAME = 'Reboots';
var INSTLOG_SHEET_NAME = 'InstLog';
// ローリング保持：直近1年分（30秒間隔 × 2 × 60分 × 24時間 × 365日）。
// ダッシュボードの表示スコープ（最大7日間）とは独立：グラフ側の裏取得は常に直近20160行
// （MAX_SCOPE_TAIL_ROWS、Dashboard.html参照）に上限を設けてあるので、ここを伸ばしても
// 表示側の通信量・読み出し時間は増えない
var INSTLOG_MAX_ROWS = 2 * 60 * 24 * 365;
// 本番InstLogとは別のシート。負荷テスト用データを置く（本番の実データには一切触れない）。
// テストは表示スコープ相当（1週間）で十分なので、INSTLOG_MAX_ROWSとは連動させない
var INSTLOG_TEST_SEED_ROWS = 20160;
var INSTLOG_TEST_SHEET_NAME = 'InstLogTest';

// 起動('boot')ごとに Reboots シート（Historyと同じスプレッドシート内の別タブ）へ日時付きで1行追記。
// 恒久蓄積（無制限）。PROPのrebootLogは直近100件のダッシュボード即時表示用、こちらが恒久記録の本体。
function appendReboot(atIso, cause, count, gapMin) {
  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000);
    var ssId = PROP.getProperty('historySpreadsheetId');
    var ss;
    if (ssId) {
      ss = SpreadsheetApp.openById(ssId);
    } else {
      ss = SpreadsheetApp.create('SMM3 History');
      PROP.setProperty('historySpreadsheetId', ss.getId());
    }
    var sheet = ss.getSheetByName(REBOOT_SHEET_NAME);
    if (!sheet) {
      sheet = ss.insertSheet(REBOOT_SHEET_NAME);
      sheet.appendRow(['at', 'cause', 'count', 'gapMin']);
    }
    sheet.appendRow([atIso, cause, count, gapMin]);
  } finally {
    lock.releaseLock();
  }
}

function getInstLogSheet() {
  var ssId = PROP.getProperty('historySpreadsheetId');
  var ss;
  if (ssId) {
    ss = SpreadsheetApp.openById(ssId);
  } else {
    ss = SpreadsheetApp.create('SMM3 History');
    PROP.setProperty('historySpreadsheetId', ss.getId());
  }

  var sheet = ss.getSheetByName(INSTLOG_SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(INSTLOG_SHEET_NAME);
    sheet.appendRow(['created', 'watt', 'amp']);
  }
  return sheet;
}

// type:'inst' 受信時に呼ぶ。親機はタイムスタンプを送ってこないため、GAS受信時刻をそのまま
// createdとして1行追記する。直近 INSTLOG_MAX_ROWS 行（既定：1年分）だけ残るよう、
// 超過した分は追記のたびに古い行から削るローリング方式（cuml/backfillのHistoryとは別シート、
// 別の保持ポリシー）。
function appendInstLog(watt, amp) {
  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000);
    var sheet = getInstLogSheet();
    sheet.appendRow([new Date(), watt, amp]);
    var dataRows = sheet.getLastRow() - 1;
    if (dataRows > INSTLOG_MAX_ROWS) {
      sheet.deleteRows(2, dataRows - INSTLOG_MAX_ROWS);
    }
  } finally {
    lock.releaseLock();
  }
}

// InstLogの実データを、ダッシュボードのInstLogグラフ用に軽量な配列形式で返す。
// [{created,watt,amp}, ...]ではなく[[epoch_ms, watt], ...]にするのは、20160行規模だと
// キー名の繰り返し(created/watt/amp)だけでJSONサイズがかなり膨らむため。ampは現状の
// グラフ表示（瞬時Wのみ）では未使用なので、まずは含めずペイロードを削る。
//
// tailRowsを指定すると末尾（＝直近）だけを読む。InstLogは追記のみ＝時刻昇順が保証されているため、
// 「末尾N行」は素直に「直近N行」になる。初期表示を軽くするため（6時間分だけ即時表示→
// 残りは裏で全期間取得）に使う。全件読むより getRange の対象行数が減る分、実際に読み出しが速くなる
// （20160行→数百〜千行程度に絞れる）。truncatedで「これは末尾だけで全部ではない」ことを返し、
// クライアント側が追加取得すべきか判断できるようにする
function readInstLogRows(tailRows) {
  return readInstLogSheetTail(getInstLogSheet(), tailRows);
}

function readInstLogSheetTail(sheet, tailRows) {
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return { points: [], truncated: false };
  var dataRows = lastRow - 1;
  var truncated = !!(tailRows && tailRows < dataRows);
  var startRow = truncated ? (lastRow - tailRows + 1) : 2;
  var numRows = truncated ? tailRows : dataRows;
  var values = sheet.getRange(startRow, 1, numRows, 2).getValues();  // created, watt の2列だけ
  var points = [];
  for (var i = 0; i < values.length; i++) {
    var created = values[i][0];
    if (!(created instanceof Date)) continue;
    points.push([created.getTime(), Math.round(values[i][1])]);
  }
  return { points: points, truncated: truncated };
}

function getInstLogTestSheet() {
  var ssId = PROP.getProperty('historySpreadsheetId');
  var ss;
  if (ssId) {
    ss = SpreadsheetApp.openById(ssId);
  } else {
    ss = SpreadsheetApp.create('SMM3 History');
    PROP.setProperty('historySpreadsheetId', ss.getId());
  }

  var sheet = ss.getSheetByName(INSTLOG_TEST_SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(INSTLOG_TEST_SHEET_NAME);
    sheet.appendRow(['created', 'watt', 'amp']);
  }
  return sheet;
}

// 負荷テスト用：直近1週間・30秒間隔(20160行)の合成データをInstLogTestシートへ一括生成する。
// GASエディタから手動実行する想定（doGet経由で誰でも起動できる形にはしない）。
// appendRowを20160回呼ぶと非常に遅い上にLockの保持時間も長くなるため、setValuesで一括書き込みする。
function seedTestInstLog() {
  var sheet = getInstLogTestSheet();
  var lastRow = sheet.getLastRow();
  if (lastRow >= 2) sheet.deleteRows(2, lastRow - 1);

  var n = INSTLOG_TEST_SEED_ROWS;
  var stepMs = 30 * 1000;
  var now = new Date();
  var startMs = now.getTime() - n * stepMs;
  var rows = new Array(n);
  for (var i = 0; i < n; i++) {
    var t = new Date(startMs + i * stepMs);
    var hour = t.getHours() + t.getMinutes() / 60;
    // Dashboard.htmlのbuildSampleData()と同じ日周パターン＋ノイズ＋時々スパイクのロジック
    var base = 250
      + 350 * Math.max(0, Math.sin((hour - 6) / 24 * Math.PI * 2 - Math.PI / 2))
      + 200 * Math.exp(-Math.pow(hour - 19, 2) / 8);
    var noise = (Math.random() - 0.5) * 120;
    var spike = (Math.random() < 0.004) ? Math.random() * 1200 : 0;
    var watt = Math.max(30, Math.round(base + noise + spike));
    var amp = Math.round(watt / 100 * 10) / 10;  // テスト表示用の目安値（実電圧換算ではない）
    rows[i] = [t, watt, amp];
  }
  sheet.getRange(2, 1, n, 3).setValues(rows);
  return 'seeded ' + n + ' rows into ' + INSTLOG_TEST_SHEET_NAME;
}

function readInstLogTestRows(tailRows) {
  return readInstLogSheetTail(getInstLogTestSheet(), tailRows);
}

function getHistorySheet() {
  var ssId = PROP.getProperty('historySpreadsheetId');
  var ss;
  if (ssId) {
    ss = SpreadsheetApp.openById(ssId);
  } else {
    ss = SpreadsheetApp.create('SMM3 History');
    PROP.setProperty('historySpreadsheetId', ss.getId());
  }

  var sheet = ss.getSheetByName(HISTORY_SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(HISTORY_SHEET_NAME);
    sheet.appendRow(['created', 'e_energy']);

    var defaultSheet = ss.getSheetByName('Sheet1');
    if (defaultSheet && ss.getSheets().length > 1) ss.deleteSheet(defaultSheet);
  }
  return sheet;
}

// type:'cuml' 受信時に呼ぶ。createdが前回保存分と同じなら追記しない（重複排除）
// Sheetに書き込んだ日時はDate型に自動変換されるため、文字列のまま比較せず
// parseCreated()で両方を正規化してから比較する
//
// LockServiceで排他制御している理由：Apps ScriptはdoPostの同時実行を許すため、
// 定時のcuml送信とbackfill送信のタイミングが重なると、互いの読み込み→書き込みが
// 競合してデータを壊す可能性がある（読み込み→削除→再書き込みの複数手順を踏むbackfill側で特に危険）。
// スクリプト全体で1つのロックを共有し、Historyシートへの書き込みを直列化する
function appendHistory(created, e_energy) {
  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000);
    var sheet = getHistorySheet();
    var lastRow = sheet.getLastRow();
    if (lastRow >= 2) {
      var lastCreated = parseCreated(sheet.getRange(lastRow, 1).getValue());
      var incoming = parseCreated(created);
      if (lastCreated && incoming && lastCreated.getTime() === incoming.getTime()) return;
    }
    sheet.appendRow([created, e_energy]);
  } finally {
    lock.releaseLock();
  }
}

// type:'backfill' 受信時に呼ぶ。created: [...], e_energy: [...] の配列2本（同じ長さ、同じ添字が対応）。
// 2026-08-09、ペイロード圧縮のため points:[{created,e_energy},...]（キー名の繰り返し）から
// この配列2本形式に変更（JSONサイズ約43%削減）。旧形式のリクエストは受け付けない。
// このチャンクに含まれる「ぴったり同じ時刻」のデータだけを新データで上書きし、
// それ以外（別の時刻・別の日、新しい/古いどちらも）はそのまま保持する。
// 親機は1日分、あるいは半日分など、複数回に分けて送ってくる想定なので、
// 日付単位ではなく時刻単位で上書き範囲を絞る必要がある
// （日付単位だと、同じ日を複数チャンクに分けて送った時に、後のチャンクが前のチャンクを消してしまう）
function backfillHistory(createdArr, eEnergyArr) {
  if (!createdArr || !eEnergyArr || createdArr.length !== eEnergyArr.length) return;

  var parsedPoints = [];
  for (var i = 0; i < createdArr.length; i++) {
    var created = parseCreated(createdArr[i]);
    var e_energy = Number(eEnergyArr[i]);
    if (created && !isNaN(e_energy)) parsedPoints.push({ created: created, e_energy: e_energy });
  }

  if (parsedPoints.length === 0) return;

  // waitLock()をtryの内側に入れる：タイムアウトで例外が飛んでもfinallyでreleaseLockに必ず到達させる
  // （外側だと例外がdoPostまで素通りし、親機の_web_post()はレスポンス本文を見ないため
  //   「送れた」扱いのまま実際には書き込まれていない、というサイレント障害になり得る）
  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000);
    var targetTimes = {};
    parsedPoints.forEach(function (p) { targetTimes[p.created.getTime()] = true; });

    var existing = readHistoryRows().filter(function (r) {
      return !targetTimes[r.created.getTime()];
    });

    var combined = existing.concat(parsedPoints);
    combined.sort(function (a, b) { return a.created - b.created; });

    var sheet = getHistorySheet();
    var lastRow = sheet.getLastRow();
    if (lastRow >= 2) sheet.deleteRows(2, lastRow - 1);

    if (combined.length > 0) {
      var values = combined.map(function (r) { return [r.created, r.e_energy]; });
      sheet.getRange(2, 1, values.length, 2).setValues(values);
    }
  } finally {
    lock.releaseLock();
  }
}

// Historyシートのデータ行（2行目以降）を全削除する。ヘッダ行は残す。
// 観測サイクルをやり直す際に、エディタからの手動実行 or clasp run で呼ぶ想定。
function clearHistory() {
  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000);
    var sheet = getHistorySheet();
    var lastRow = sheet.getLastRow();
    if (lastRow >= 2) sheet.deleteRows(2, lastRow - 1);
    return 'cleared rows 2..' + lastRow;
  } finally {
    lock.releaseLock();
  }
}

// created昇順でソート済みのものを返す（buildDayProfile等が日付境界を跨いで
// 前後を参照するため、呼び出し側で毎回ソートし直さずに済むよう、ここで保証する）
function readHistoryRows() {
  var sheet = getHistorySheet();
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];
  var values = sheet.getRange(2, 1, lastRow - 1, 2).getValues();
  var rows = [];
  for (var i = 0; i < values.length; i++) {
    var created = parseCreated(values[i][0]);
    var e_energy = Number(values[i][1]);
    if (created && !isNaN(e_energy)) rows.push({ created: created, e_energy: e_energy });
  }
  rows.sort(function (a, b) { return a.created - b.created; });
  return rows;
}

function parseCreated(v) {
  if (v instanceof Date) return v;
  var m = String(v).match(/(\d+)-(\d+)-(\d+) (\d+):(\d+):(\d+)/);
  if (!m) return null;
  return new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]);
}

function dayKey(d) {
  return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
}

function pad2(n) {
  return (n < 10 ? '0' : '') + n;
}

// 指定日の0:00〜24:00、30分刻み(0〜48)の境界時刻における累積値（無ければ直前値を引き継ぐ、無ければnull）
//
// 親機からのバックフィルは1日分をk=0(00:00)〜47(23:30)の48点しか送らない（24:00時点＝翌日0:00時点の
// 値は翌日分のデータとして送られる）。そのため境界の検索は「その日のデータだけ」に絞らず、
// rows全体（readHistoryRowsでcreated昇順ソート済み）を素直に辿る。これにより最後の境界(i=48)は
// 翌日0:00の行から正しく取得でき、最終スロット(23:30〜24:00)が前の値のコピー＝差分0になって
// バーが描かれない問題（H2検証時に発見）を避けられる。
function buildDayProfile(rows, dayKeyStr) {
  var dayRows = rows.filter(function (r) { return dayKey(r.created) === dayKeyStr; });
  if (dayRows.length === 0) return null;

  var base = dayRows[0].created;
  var boundaries = [];
  var di = 0;
  var val = null;
  for (var i = 0; i <= 48; i++) {
    var slotTime = new Date(base.getFullYear(), base.getMonth(), base.getDate(), 0, i * 30, 0);
    while (di < rows.length && rows[di].created <= slotTime) {
      val = rows[di].e_energy;
      di++;
    }
    boundaries.push(val);
  }
  return boundaries;
}

// 値が0（または無し）の境界は「実データではない」として扱う。
// メーター交換等で当該時刻の累積値がまだ記録されていない場合、boundaryは0として残るため
// （境界探索の初期値valがnullのまま渡されるケースと区別がつかない）、子機の各種チェック
// （hist_data[...]==0 を「データ無し」として弾く判定）と同じ意味でnullと同様に扱う
function noVal(v) {
  return v == null || v === 0;
}

function profileToSlots(boundaries) {
  var slots = [];
  for (var i = 0; i < 48; i++) {
    var a = boundaries[i], b = boundaries[i + 1];
    slots.push((noVal(a) || noVal(b)) ? null : round2(b - a));
  }
  return slots;
}

function profileToHourly(boundaries) {
  var hourly = [];
  for (var h = 0; h < 24; h++) {
    var a = boundaries[h * 2], b = boundaries[(h + 1) * 2];
    hourly.push((noVal(a) || noVal(b)) ? null : round2(b - a));
  }
  return hourly;
}

// 子機のdraw_graph()と同じく「0:00時点の値が0（メーター交換等でまだ実測値が無い）」なら
// その日全体を集計対象から除外する（中途半端な日を、平均や日別バーに混ぜて歪ませないため）
function dailyTotal(rows, dayKeyStr) {
  var b = buildDayProfile(rows, dayKeyStr);
  if (!b || noVal(b[0]) || b[48] == null) return null;
  return round2(b[48] - b[0]);
}

function realToday(rows, now) {
  var todayB = buildDayProfile(rows, dayKey(now));
  var y = new Date(now); y.setDate(y.getDate() - 1);
  var yestB = buildDayProfile(rows, dayKey(y));
  return {
    today: todayB ? profileToSlots(todayB) : new Array(48).fill(null),
    yesterday: yestB ? profileToSlots(yestB) : new Array(48).fill(null)
  };
}

// 指定日の0:00〜「nowと同じ時刻」までの部分集計（smm3_sub_core2.pyのhist_data[n][index]-hist_data[n][0]相当）。
// nowが今日なら「現在時刻までの累計」、過去日なら「その日の同じ時刻までの累計」になり、
// 今日の進捗とフェアに比較できる（draw_graph()のdaily_sub_t/today_sub_tと同じ考え方）
function daySubTotal(rows, dayKeyStr, now) {
  var b = buildDayProfile(rows, dayKeyStr);
  if (!b || noVal(b[0])) return null;
  var idx = Math.min(48, Math.floor((now.getHours() * 60 + now.getMinutes()) / 30));
  if (b[idx] == null) return null;
  return round2(b[idx] - b[0]);
}

// 直近period日間（今日を含まない、D-1が先頭）について、各日の「現在時刻までの部分集計」と
// 「終日の合計」の両方、および今日の部分集計、両者それぞれの平均を返す。
// 子機のdraw_graph()と同じく、「今日」「平均」は日毎の並びから分離した別バーとして扱う
function periodSummary(rows, now, period) {
  var days = [];
  for (var i = 1; i <= period; i++) {
    var d = new Date(now); d.setDate(d.getDate() - i);
    var dk = dayKey(d);
    days.push({
      date: fmtMD(d),
      sub: daySubTotal(rows, dk, now),
      total: dailyTotal(rows, dk)
    });
  }

  var validSub = days.map(function (x) { return x.sub; }).filter(function (t) { return t != null; });
  var validTotal = days.map(function (x) { return x.total; }).filter(function (t) { return t != null; });
  var avgSub = validSub.length ? round2(validSub.reduce(function (a, b) { return a + b; }, 0) / validSub.length) : null;
  var avgTotal = validTotal.length ? round2(validTotal.reduce(function (a, b) { return a + b; }, 0) / validTotal.length) : null;

  return {
    today: daySubTotal(rows, dayKey(now), now),
    days: days,
    avgSub: avgSub,
    avgTotal: avgTotal
  };
}

function realWeek(rows, now) {
  return periodSummary(rows, now, 7);
}

function realMonth(rows, now) {
  return periodSummary(rows, now, 30);
}

function fmtMD(d) {
  return (d.getMonth() + 1) + '/' + d.getDate();
}

// 過去days日間（今日を含まない）の時間別平均プロファイル。データが無い時間はnull
function avgHourlyProfile(rows, now, days) {
  var sums = new Array(24).fill(0);
  var counts = new Array(24).fill(0);
  for (var i = 1; i <= days; i++) {
    var d = new Date(now); d.setDate(d.getDate() - i);
    var b = buildDayProfile(rows, dayKey(d));
    if (!b) continue;
    var hourly = profileToHourly(b);
    for (var h = 0; h < 24; h++) {
      if (hourly[h] != null) { sums[h] += hourly[h]; counts[h]++; }
    }
  }
  // round1（Code.js定義）：Dashboard.htmlの表示桁(toFixed(1))に揃える。子機のdraw_table()も
  // 1桁丸め後の値を積算しているため、「表示行を目で足すと合計と合わない」見た目の矛盾を防ぐ
  // 目的でここも1桁に統一（2026-08-11）
  return sums.map(function (s, h) { return counts[h] ? round1(s / counts[h]) : null; });
}
