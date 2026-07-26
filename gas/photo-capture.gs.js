/**
 * wtul phone photo capture endpoint (ROADMAP #4).
 *
 * Bespoke doGet/doPost shape, NOT the bug/feature/resolve contract in the
 * scheduler's INTAKE.md - see lib/photo_capture.py's module docstring for
 * why that shape doesn't fit "one photo, tied to one disc, consumed
 * once." Open question for the user (see .claude/QUESTIONS.md): deploy
 * this standalone (as built here), or fold it into the existing GAS
 * project already backing the ROADMAP #4 sheet - this session had no way
 * to read that project's live Apps Script source to check.
 *
 * Deploy: Deploy > New deployment > type "Web app" > Execute as "Me",
 * Who has access "Anyone" > Deploy > copy the /exec URL into
 * PHOTO_CAPTURE_URL in ~/.config/wtul/secrets.env.
 *
 * Flow:
 *   1. wtul-rip generates a pairing code + disc id at rip time, builds
 *      a URL to this endpoint (see lib/photo_capture.py's pairing_url),
 *      and shows/prints it (a QR code once #3's label printer is wired
 *      up to do so - not built yet).
 *   2. Phone opens that URL -> GET with no `scope` param -> serves the
 *      HTML upload form below, camera-capture input pre-filled with the
 *      pairing code + disc id.
 *   3. The form's JS POSTs the photo as base64 straight to this same
 *      /exec URL. doPost saves it to Drive, makes it link-viewable, and
 *      appends a row to the PHOTOS sheet tab.
 *   4. wtul-rip polls GET ?scope=photo&pairing_code=... until it finds
 *      the row, downloads the image, embeds it as ID3 art.
 *
 * Read:
 *   ?scope=photo&pairing_code=X -> {found, url, disc_id, created_at} or
 *                                  {found:false}
 *   ?scope=tabs / ?scope=debug / ?scope=schema -> same shape as
 *   catalog-writeback.gs.js, for sanity-checking the PHOTOS tab layout.
 *
 * Write (POST, Content-Type: text/plain, JSON body):
 *   {"pairing_code", "disc_id", "image_base64", "mime"} -> saves the
 *   image to Drive, appends {PAIRING_CODE, DISC_ID, DRIVE_FILE_ID, URL,
 *   CREATED_AT} to the PHOTOS tab. Same never-trust-the-raw-POST-
 *   response gotcha as catalog-writeback.gs.js applies to callers here
 *   too - poll the GET side to confirm, don't trust doPost's own return.
 */

var SHEET_NAME = "PHOTOS";
var DRIVE_FOLDER_NAME = "wtul-photo-capture";
var HEADER_SCAN_ROWS = 5;

function _sheet() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
    sheet.appendRow(["PAIRING_CODE", "DISC_ID", "DRIVE_FILE_ID", "URL", "CREATED_AT"]);
  }
  return sheet;
}

function _folder() {
  var it = DriveApp.getFoldersByName(DRIVE_FOLDER_NAME);
  return it.hasNext() ? it.next() : DriveApp.createFolder(DRIVE_FOLDER_NAME);
}

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

  if (!scope && e.parameter.pairing_code) {
    return _uploadPage(e.parameter.pairing_code, e.parameter.disc_id || '');
  }

  if (scope === 'tabs') {
    var names = SpreadsheetApp.getActiveSpreadsheet().getSheets().map(function (s) {
      return s.getName();
    });
    return _json({ tabs: names });
  }

  var sheet = _sheet();

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

  if (scope === 'photo') {
    var code = String(e.parameter.pairing_code || '').trim();
    if (!code) return _json({ found: false, error: 'missing pairing_code' });
    var d = _detectHeaderRow(sheet);
    var headers = d.headers;
    var lastRowN = sheet.getLastRow();
    var firstDataRow = d.rowIndex + 1;
    if (lastRowN < firstDataRow) return _json({ found: false });
    var values = sheet.getRange(firstDataRow, 1, lastRowN - firstDataRow + 1, headers.length).getValues();
    var codeIdx = headers.indexOf('PAIRING_CODE');
    var urlIdx = headers.indexOf('URL');
    var discIdx = headers.indexOf('DISC_ID');
    var createdIdx = headers.indexOf('CREATED_AT');
    for (var i = values.length - 1; i >= 0; i--) {
      if (String(values[i][codeIdx]).trim() === code) {
        return _json({
          found: true,
          url: values[i][urlIdx],
          disc_id: values[i][discIdx],
          created_at: values[i][createdIdx]
        });
      }
    }
    return _json({ found: false });
  }

  return _json({ error: 'unknown scope, use ?scope=tabs|debug|schema|photo' });
}

function doPost(e) {
  var data;
  try {
    data = JSON.parse(e.postData.contents);
  } catch (err) {
    return _json({ error: 'body was not valid JSON' });
  }

  var pairingCode = String(data.pairing_code || '').trim();
  var discId = String(data.disc_id || '').trim();
  var imageBase64 = data.image_base64;
  var mime = data.mime || 'image/jpeg';

  if (!pairingCode || !imageBase64) {
    return _json({ error: 'pairing_code and image_base64 are required' });
  }

  var bytes = Utilities.base64Decode(imageBase64);
  var blob = Utilities.newBlob(bytes, mime, pairingCode + '.jpg');
  var file = _folder().createFile(blob);
  file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  var url = 'https://drive.google.com/uc?export=view&id=' + file.getId();

  var sheet = _sheet();
  sheet.appendRow([pairingCode, discId, file.getId(), url,
                   Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyy-MM-dd'T'HH:mm:ss")]);

  return _json({ ok: true, url: url, driveFileId: file.getId() });
}

function _uploadPage(pairingCode, discId) {
  var template = HtmlService.createTemplateFromFile('upload');
  template.pairingCode = pairingCode;
  template.discId = discId;
  return template.evaluate();
}

function _json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
