/**
 * wtul catalog write-back endpoint.
 *
 * Bound to the catalog spreadsheet (Extensions > Apps Script from the
 * sheet itself). Appends a row per POST, matching JSON fields to columns
 * by the sheet's own header row (row 1) - so it doesn't need to know your
 * schema in advance, and adding/renaming a column later needs no script
 * change, just a matching key in what wtul-rip sends.
 *
 * Deploy: Deploy > New deployment > type "Web app" > Execute as "Me",
 * Who has access "Anyone" > Deploy > copy the /exec URL, send it back.
 *
 * Write: POST, Content-Type: text/plain, body a JSON object of
 * {"Column Name": value, ...} - keys must match header text exactly
 * (case-insensitive, whitespace-trimmed). Unmatched keys are ignored,
 * not errored - so a partial disc scrape can still write what it has.
 *
 * Read: GET ?scope=schema -> {"headers": [...]} so wtul can see the
 * actual column names once, instead of guessing.
 * GET ?scope=rows&limit=N -> last N rows as objects, for the
 * never-trust-the-raw-POST-response gotcha (re-GET to confirm a write
 * landed - see the scheduler's INTAKE.md for why).
 */
function _sheet() {
  return SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
}

function _headers(sheet) {
  var lastCol = sheet.getLastColumn();
  if (lastCol === 0) return [];
  return sheet.getRange(1, 1, 1, lastCol).getValues()[0];
}

function doGet(e) {
  var scope = (e.parameter.scope || '').toLowerCase();
  var sheet = _sheet();

  if (scope === 'schema') {
    return _json({ headers: _headers(sheet) });
  }

  if (scope === 'rows') {
    var limit = parseInt(e.parameter.limit, 10) || 20;
    var headers = _headers(sheet);
    var lastRow = sheet.getLastRow();
    if (lastRow < 2) return _json({ rows: [] });
    var startRow = Math.max(2, lastRow - limit + 1);
    var numRows = lastRow - startRow + 1;
    var values = sheet.getRange(startRow, 1, numRows, headers.length).getValues();
    var rows = values.map(function (row) {
      var obj = {};
      headers.forEach(function (h, i) { obj[h] = row[i]; });
      return obj;
    });
    return _json({ rows: rows });
  }

  return _json({ error: 'unknown scope, use ?scope=schema or ?scope=rows' });
}

function doPost(e) {
  var sheet = _sheet();
  var headers = _headers(sheet);
  if (headers.length === 0) {
    return _json({ error: 'sheet has no header row (row 1) - add column names first' });
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
