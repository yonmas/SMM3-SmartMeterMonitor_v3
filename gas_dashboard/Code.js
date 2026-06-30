// SMM3 Dashboard - GAS Web App
// 親機からの M:CUML / M:INST 相当のデータを受け取って表示する。

var PROP = PropertiesService.getScriptProperties();

function doGet(e) {
  if (e.parameter.action === 'data') {
    return ContentService.createTextOutput(JSON.stringify(getDashboardData()))
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
  }
  return ContentService.createTextOutput('OK');
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
    }
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
