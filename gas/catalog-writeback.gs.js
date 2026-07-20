/**
 * wtul catalog write-back endpoint.
 *
 * Bound to the catalog spreadsheet (Extensions > Apps Script from the
 * sheet itself). Appends a row per POST, matching JSON fields to columns
 * by the sheet's own header row - so it doesn't need to know your schema
 * in advance, and adding/renaming a column later needs no script change,
 * just a matching key in what wtul-rip sends.
 *
 * Deploy: Deploy > New deployment > type "Web app" > Execute as "Me",
 * Who has access "Anyone" > Deploy > copy the /exec URL, send it back.
 * Redeploy (same code, new logic): Deploy > Manage deployments > Edit
 * (pencil) > Version: New version > Deploy - keeps the same /exec URL.
 *
 * Write: POST, Content-Type: text/plain, body a JSON object of
 * {"Column Name": value, ...} - keys must match header text exactly
 * (case-insensitive, whitespace-trimmed). Unmatched keys are ignored,
 * not errored - so a partial disc scrape can still write what it has.
 *
 * Read:
 *   ?scope=tabs   -> every sheet/tab name in this spreadsheet, so the
 *                    right one can be picked by name below if it isn't
 *                    the first tab.
 *   ?scope=debug  -> {sheetName, headerRow, headers, sampleRows} - the
 *                    first several raw rows of whichever sheet is in use
 *                    and which row got auto-detected as the header row,
 *                    for sanity-checking a sheet whose layout wasn't what
 *                    was expected (e.g. a title row before the real
 *                    headers).
 *   ?scope=schema -> {headers: [...]}
 *   ?scope=rows&limit=N -> last N rows as objects, for the
 *                    never-trust-the-raw-POST-response gotcha (re-GET to
 *                    confirm a write landed - see the scheduler's
 *                    INTAKE.md for why).
 */

// If the target sheet isn't the first tab, set its exact name here (see
// ?scope=tabs for the list) - leave "" to use the first tab.
var SHEET_NAME = "";

// How many leading rows to scan when auto-detecting the header row (some
// sheets have a title row, or a blank row, before the real headers).
var HEADER_SCAN_ROWS = 5;

function _sheet() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  return SHEET_NAME ? ss.getSheetByName(SHEET_NAME) : ss.getSheets()[0];
}

/** The header row is whichever of the first HEADER_SCAN_ROWS rows has the
 * most non-empty cells (a title row like "LOCAL CDS" alone in column A
 * has 1; a real header row has many) - returns {rowIndex, headers}, both
 * 1-indexed rowIndex and headers possibly empty if the sheet is empty. */
function _detectHeaderRow(sheet) {
  var lastCol = sheet.getLastColumn();
  if (lastCol === 0) return { rowIndex: 1, headers: [] };
  var scanRows = Math.min(HEADER_SCAN_ROWS, sheet.getLastRow() || 1);
  var best = { rowIndex: 1, headers: [], nonEmpty: -1 };
  for (var r = 1; r <= scanRows; r++) {
    var vals = sheet.getRange(r, 1, 1, lastCol).getValues()[0];
    var nonEmpty = vals.filter(function (v) { return String(v).trim() !== ''; }).length;
    if (nonEmpty > best.nonEmpty) {
      best = { rowIndex: r, headers: vals, nonEmpty: nonEmpty };
    }
  }
  return { rowIndex: best.rowIndex, headers: best.headers };
}

function doGet(e) {
  var scope = (e.parameter.scope || '').toLowerCase();

  if (scope === 'tabs') {
    var names = SpreadsheetApp.getActiveSpreadsheet().getSheets().map(function (s) {
      return s.getName();
    });
    return _json({ tabs: names });
  }

  var sheet = _sheet();
  if (!sheet) return _json({ error: 'SHEET_NAME "' + SHEET_NAME + '" not found - check ?scope=tabs' });

  if (scope === 'debug') {
    var detected = _detectHeaderRow(sheet);
    var lastCol = sheet.getLastColumn();
    var lastRow = sheet.getLastRow();
    var sampleCount = Math.min(HEADER_SCAN_ROWS + 3, lastRow);
    var sample = sampleCount > 0 && lastCol > 0
      ? sheet.getRange(1, 1, sampleCount, lastCol).getValues()
      : [];
    return _json({
      sheetName: sheet.getName(),
      headerRowIndex: detected.rowIndex,
      headers: detected.headers,
      sampleRows: sample
    });
  }

  if (scope === 'schema') {
    return _json({ headers: _detectHeaderRow(sheet).headers });
  }

  if (scope === 'rows') {
    var limit = parseInt(e.parameter.limit, 10) || 20;
    var d = _detectHeaderRow(sheet);
    var headers = d.headers;
    var lastRowN = sheet.getLastRow();
    var firstDataRow = d.rowIndex + 1;
    if (lastRowN < firstDataRow) return _json({ rows: [] });
    var startRow = Math.max(firstDataRow, lastRowN - limit + 1);
    var numRows = lastRowN - startRow + 1;
    var values = sheet.getRange(startRow, 1, numRows, headers.length).getValues();
    var rows = values.map(function (row) {
      var obj = {};
      headers.forEach(function (h, i) { obj[h] = row[i]; });
      return obj;
    });
    return _json({ rows: rows });
  }

  return _json({ error: 'unknown scope, use ?scope=tabs|debug|schema|rows' });
}

function doPost(e) {
  var sheet = _sheet();
  if (!sheet) return _json({ error: 'SHEET_NAME "' + SHEET_NAME + '" not found - check ?scope=tabs' });

  var detected = _detectHeaderRow(sheet);
  var headers = detected.headers;
  if (headers.length === 0) {
    return _json({ error: 'no header row detected - add column names first, see ?scope=debug' });
  }

  var data;
  try {
    data = JSON.parse(e.postData.contents);
  } catch (err) {
    return _json({ error: 'body was not valid JSON' });
  }

  // Case-insensitive, trimmed match of incoming keys to header text.
  var normalizedHeaders = headers.map(function (h) {
    return String(h).trim().toLowerCase();
  });

  var row = new Array(headers.length).fill('');
  var matched = [];
  var unmatched = [];
  Object.keys(data).forEach(function (key) {
    var idx = normalizedHeaders.indexOf(key.trim().toLowerCase());
    if (idx === -1) {
      unmatched.push(key);
    } else {
      row[idx] = data[key];
      matched.push(headers[idx]);
    }
  });

  sheet.appendRow(row);

  return _json({
    ok: true,
    rowWritten: sheet.getLastRow(),
    matchedColumns: matched,
    unmatchedKeys: unmatched
  });
}

function _json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
