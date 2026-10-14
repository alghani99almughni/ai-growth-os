/**
 * AI Growth OS SmartCheck / SnapSheet compatibility bridge.
 * Deploy as a Google Apps Script web app. Configure Script Properties:
 * AI_GROWTH_OS_API_KEY, SPREADSHEET_ID, and optionally DRIVE_FOLDER_ID.
 */
const SHEET_NAME = "VisitorLog";
const ACTION_LOG_SHEET = "ActionLog";
const HEADERS = [
  "Tenant ID", "Ticket ID", "Visitor Name", "Mobile", "Purpose",
  "Target Destination", "Vehicle Number", "Snapshot Link", "Status",
  "Approver Name", "QR Token", "Gate Entry Time", "Gate Exit Time",
  "Created At", "Updated At", "Remarks"
];

function output_(value) {
  return ContentService.createTextOutput(JSON.stringify(value))
    .setMimeType(ContentService.MimeType.JSON);
}

function props_() {
  const p = PropertiesService.getScriptProperties();
  if (!p.getProperty("AI_GROWTH_OS_API_KEY")) throw new Error("AI_GROWTH_OS_API_KEY is not configured");
  return p;
}

function authorize_(data) {
  const expected = props_().getProperty("AI_GROWTH_OS_API_KEY");
  const supplied = String((data && data.apiKey) || "");
  if (!supplied || supplied !== expected) throw new Error("UNAUTHORIZED");
}

function spreadsheet_() {
  const p = props_();
  const id = p.getProperty("SPREADSHEET_ID");
  const ss = id ? SpreadsheetApp.openById(id) : SpreadsheetApp.getActiveSpreadsheet();
  if (!ss) throw new Error("Set SPREADSHEET_ID in Script Properties");
  return ss;
}

function visitorSheet_() {
  const ss = spreadsheet_();
  let sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) sheet = ss.insertSheet(SHEET_NAME);
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(HEADERS);
    sheet.getRange(1, 1, 1, HEADERS.length).setFontWeight("bold");
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function driveFolder_() {
  const p = props_();
  const id = p.getProperty("DRIVE_FOLDER_ID");
  if (id) return DriveApp.getFolderById(id);
  const name = "SmartCheckPasses";
  const folders = DriveApp.getFoldersByName(name);
  return folders.hasNext() ? folders.next() : DriveApp.createFolder(name);
}

function rowObject_(row) {
  return {
    tenantId: String(row[0] || ""),
    ticketId: String(row[1] || ""),
    visitorName: String(row[2] || ""),
    visitorMobile: String(row[3] || ""),
    purpose: String(row[4] || ""),
    targetDestination: String(row[5] || ""),
    vehicleNumber: String(row[6] || ""),
    vehicleSnapshotUri: String(row[7] || ""),
    status: String(row[8] || "PENDING_APPROVAL"),
    approverName: String(row[9] || ""),
    qrToken: String(row[10] || ""),
    gateEntryTime: String(row[11] || ""),
    gateExitTime: String(row[12] || ""),
    createdAt: String(row[13] || ""),
    updatedAt: String(row[14] || ""),
    remarks: String(row[15] || "")
  };
}

function findTicketRow_(sheet, tenantId, ticketId) {
  const last = sheet.getLastRow();
  if (last < 2) return -1;
  const rows = sheet.getRange(2, 1, last - 1, HEADERS.length).getValues();
  for (let i = 0; i < rows.length; i++) {
    if (String(rows[i][0]) === String(tenantId) && String(rows[i][1]) === String(ticketId)) return i + 2;
  }
  return -1;
}

function saveTicket_(data) {
  if (!data.tenantId || !data.ticketId || !data.visitorName) {
    throw new Error("tenantId, ticketId and visitorName are required");
  }
  const sheet = visitorSheet_();
  let snapshot = String(data.vehicleSnapshotUri || "");
  if (data.imageBase64 && String(data.imageBase64).length > 50) {
    const blob = Utilities.newBlob(
      Utilities.base64Decode(String(data.imageBase64)),
      "image/jpeg",
      String(data.ticketId).replace(/[^a-zA-Z0-9_-]/g, "_") + ".jpg"
    );
    snapshot = driveFolder_().createFile(blob).getUrl();
  }
  const now = new Date().toISOString();
  const row = [
    String(data.tenantId), String(data.ticketId), String(data.visitorName),
    String(data.visitorMobile || ""), String(data.purpose || ""),
    String(data.targetDestination || ""), String(data.vehicleNumber || ""),
    snapshot, String(data.status || "PENDING_APPROVAL"),
    String(data.approverName || ""), "", String(data.gateEntryTime || ""),
    String(data.gateExitTime || ""), String(data.createdAt || now),
    String(data.updatedAt || now), String(data.remarks || "")
  ];
  const existing = findTicketRow_(sheet, data.tenantId, data.ticketId);
  if (existing > 0) sheet.getRange(existing, 1, 1, HEADERS.length).setValues([row]);
  else sheet.appendRow(row);
  return { status: "success", ticketId: String(data.ticketId), snapshotUrl: snapshot };
}

function updateDecision_(data, status) {
  if (!data.tenantId || !data.ticketId) throw new Error("tenantId and ticketId are required");
  const sheet = visitorSheet_();
  const row = findTicketRow_(sheet, data.tenantId, data.ticketId);
  if (row < 0) throw new Error("TICKET_NOT_FOUND");
  sheet.getRange(row, 9).setValue(status);
  sheet.getRange(row, 10).setValue(String(data.approverName || ""));
  sheet.getRange(row, 16).setValue(String(data.remarks || ""));
  sheet.getRange(row, 15).setValue(new Date().toISOString());
  return { status: "success", ticketId: String(data.ticketId), ticketStatus: status };
}

function logAction_(data) {
  const ss = spreadsheet_();
  let sheet = ss.getSheetByName(ACTION_LOG_SHEET);
  if (!sheet) sheet = ss.insertSheet(ACTION_LOG_SHEET);
  if (sheet.getLastRow() === 0) sheet.appendRow(["Timestamp", "Tenant ID", "Ticket ID", "Actor", "Action", "Remarks"]);
  sheet.appendRow([
    new Date().toISOString(), String(data.tenantId || ""), String(data.ticketId || ""),
    String(data.approverName || ""), String(data.action || "LOG_ACTION"), String(data.remarks || "")
  ]);
  return { status: "success" };
}

function doGet(e) {
  try {
    const params = (e && e.parameter) || {};
    authorize_(params);
    const action = String(params.action || "PING").toUpperCase();
    if (action === "PING" || action === "TEST_PING") {
      visitorSheet_();
      driveFolder_();
      return output_({ status: "ok", message: "Google Sheets and Drive are ready" });
    }
    if (action === "GET_PENDING_APPROVALS") {
      if (!params.tenantId) throw new Error("tenantId is required");
      const sheet = visitorSheet_();
      const last = sheet.getLastRow();
      const rows = last < 2 ? [] : sheet.getRange(2, 1, last - 1, HEADERS.length).getValues();
      const tickets = rows.map(rowObject_).filter(t =>
        t.tenantId === String(params.tenantId) &&
        ["PENDING", "PENDING_APPROVAL", "PENDING APPROVAL", "AWAITING_APPROVAL"].includes(t.status.toUpperCase())
      );
      return output_({ status: "success", count: tickets.length, tickets: tickets });
    }
    return output_({ status: "error", message: "Unsupported action" });
  } catch (err) {
    return output_({ status: "error", message: String(err.message || err) });
  }
}

function doPost(e) {
  try {
    const data = JSON.parse((e && e.postData && e.postData.contents) || "{}");
    authorize_(data);
    const action = String(data.action || "").toUpperCase();
    if (action === "PING" || action === "TEST_PING") {
      visitorSheet_();
      driveFolder_();
      return output_({ status: "ok", message: "Google Sheets and Drive are ready" });
    }
    if (action === "SYNC_TICKET") return output_(saveTicket_(data));
    if (action === "APPROVE_TICKET") return output_(updateDecision_(data, "APPROVED"));
    if (action === "REJECT_TICKET") return output_(updateDecision_(data, "REJECTED"));
    if (action === "LOG_ACTION") return output_(logAction_(data));
    return output_({ status: "error", message: "Unsupported action" });
  } catch (err) {
    const message = String(err.message || err);
    return output_({ status: "error", message: message, code: message === "UNAUTHORIZED" ? 401 : 400 });
  }
}
