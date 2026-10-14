// SmartCheck Gate Pass — hardened Apps Script bridge
// Script Properties required: AI_GROWTH_OS_BRIDGE_SECRET
// Set the same long random value as Render's AI_GROWTH_OS_BRIDGE_SECRET.
// Never put this secret in frontend code, QR codes, or URL query parameters.

const TENANTS="MultipleTenantRegister", USERS="AuthorizedUsers", LOGS="GatePassLogs";
const DRIVE_FOLDER="SmartCheckPasses";

function initialSetup(){
  const ss=SpreadsheetApp.getActiveSpreadsheet();
  const ts=ensureSheet_(ss,TENANTS,["Tenant Code","Organization Name","Category","Assigned Role","Contact Person","Email ID","Mobile Number","Reception Clearance","Staff Details","App URL","Spreadsheet URL","Registered At","Status"]);
  const us=ensureSheet_(ss,USERS,["Email","Name","Role","Designation","Status","Tenant ID","RegisteredAt"]);
  ensureSheet_(ss,LOGS,["Date","Ticket ID","Tenant Name","Visitor Name","Mobile","Purpose","Target Destination","Vehicle Number","Status","Approver Name","QR Token","Snapshot Link","Tenant ID","Updated At","Updated By","Notes"]);
  // Preserve original setup behavior: seed demo records only when the sheets are empty.
  const now=new Date().toISOString();
  if(ts.getLastRow()<=1){
    ts.appendRow(["TNT-101","Greenwood High School","School","Tenant Administrator","Principal Sharma","admin@greenwood.edu","9444444444","ENABLED","Gate Security Vikram, Reception Desk","https://ai-growth-os-web.onrender.com",ss.getUrl(),now,"ACTIVE"]);
    ts.appendRow(["TNT-102","Prestige Tech Cloud Towers","Corporate IT Park","Tenant Administrator","Facility Manager Rahul","facility@prestigetowers.com","9888888888","ENABLED","Tower A Gate, Tower B Gate","https://ai-growth-os-web.onrender.com",ss.getUrl(),now,"ACTIVE"]);
  }
  if(us.getLastRow()<=1){
    us.appendRow(["shukurhustle@gmail.com","Syed Shukur","OWNER","Developer Admin","ACTIVE","TNT-101",now]);
    us.appendRow(["gate@greenwood.edu","Officer Vikram S","SECURITY","Main Gate Post #1","ACTIVE","TNT-101",now]);
    us.appendRow(["reception@greenwood.edu","Pooja Front Desk","RECEPTION","Lobby Desk","ACTIVE","TNT-101",now]);
    us.appendRow(["principal@greenwood.edu","Principal Sharma","APPROVER","School Principal","ACTIVE","TNT-101",now]);
    us.appendRow(["security@prestigetowers.com","Security Main Gate","SECURITY","Main Gate Alpha","ACTIVE","TNT-102",now]);
  }
  folder_(DRIVE_FOLDER);
  return "Required sheets checked; existing rows preserved.";
}
function onOpen(){
  SpreadsheetApp.getUi().createMenu("🚀 SmartCheck")
    .addItem("Check / Create Required Sheets","initialSetup")
    .addSeparator().addItem("Create New Tenant","promptCreateTenant")
    .addItem("Add Staff / Role","promptAddUser").addToUi();
}
function doGet(e){
  const a=String(e&&e.parameter&&e.parameter.action||"").toUpperCase();
  if(a==="HEALTH") return out_({status:"ok",service:"SmartCheck",timestamp:new Date().toISOString()});
  return out_({status:"error",message:"Use the authenticated server API."});
}
function doPost(e){
  try{
    const d=JSON.parse(e&&e.postData&&e.postData.contents||"{}");
    const a=String(d.action||"").toUpperCase();
    if(!trusted_(d.bridgeSecret)) return out_({status:"error",message:"Unauthorized"});
    const ss=SpreadsheetApp.getActiveSpreadsheet();
    const role=role_(d.actorRole);
    const actorTenant=clean_(d.actorTenantId||d.actorTenantCode,100);
    const targetTenant=clean_(d.tenantId||d.tenantCode,100);
    switch(a){
      case "PING": return out_({status:"ok",message:"SmartCheck bridge connected",spreadsheetUrl:ss.getUrl()});
      case "SETUP": requireRole_(role,["PLATFORM_ADMIN","SUPER_ADMIN"]); initialSetup(); return out_({status:"ok",message:"Sheets checked; existing rows preserved."});
      case "GET_TENANTS": requireRole_(role,["PLATFORM_ADMIN","SUPER_ADMIN"]); return getTenants_();
      case "GET_USERS":
        requireRole_(role,["PLATFORM_ADMIN","SUPER_ADMIN","TENANT_ADMIN","OWNER"]);
        if(role!=="PLATFORM_ADMIN"&&role!=="SUPER_ADMIN"&&(!targetTenant||targetTenant!==actorTenant))throw new Error("Tenant access denied");
        return getUsers_(role==="PLATFORM_ADMIN"||role==="SUPER_ADMIN"?"":targetTenant);
      case "REGISTER_TENANT": case "CREATE_TENANT":
        requireRole_(role,["PLATFORM_ADMIN","SUPER_ADMIN"]); return registerTenant_(d);
      case "ADD_USER":
        requireRole_(role,["PLATFORM_ADMIN","SUPER_ADMIN","TENANT_ADMIN","OWNER"]);
        if(role!=="PLATFORM_ADMIN"&&role!=="SUPER_ADMIN"&&(!targetTenant||targetTenant!==actorTenant))throw new Error("Tenant access denied");
        if(role!=="PLATFORM_ADMIN"&&role!=="SUPER_ADMIN"&&["OWNER","PLATFORM_ADMIN","SUPER_ADMIN"].indexOf(role_(d.role))>=0)throw new Error("Cannot grant platform role");
        return addUser_(d.email,d.name,d.role,d.designation,targetTenant);
      case "LOGIN": case "CHECK_AUTH": return out_({status:"error",message:"Email-only authentication is disabled. Authenticate through AI Growth OS first."});
      case "VISITOR_REQUEST":
        requireRole_(role,["PLATFORM_ADMIN","SUPER_ADMIN","TENANT_ADMIN","OWNER","APPROVER","RECEPTION","SECURITY","VISITOR"]);
        requireTenantScope_(role,actorTenant,targetTenant); return visitorRequest_(d);
      case "LIST_VISITORS":
        requireRole_(role,["PLATFORM_ADMIN","SUPER_ADMIN","TENANT_ADMIN","OWNER","APPROVER","RECEPTION","SECURITY"]);
        requireTenantScope_(role,actorTenant,targetTenant); return listVisitors_(d);
      case "VERIFY_TOKEN":
        requireRole_(role,["PLATFORM_ADMIN","SUPER_ADMIN","TENANT_ADMIN","OWNER","APPROVER","RECEPTION","SECURITY"]);
        requireTenantScope_(role,actorTenant,targetTenant); return verifyVisitorToken_(d);
      case "APPROVE_VISITOR": case "REJECT_VISITOR":
        requireRole_(role,["PLATFORM_ADMIN","SUPER_ADMIN","TENANT_ADMIN","OWNER","APPROVER"]);
        requireTenantScope_(role,actorTenant,targetTenant); return visitorTransition_(d,a==="APPROVE_VISITOR"?"APPROVED":"REJECTED");
      case "CHECK_IN": case "CHECK_OUT":
        requireRole_(role,["PLATFORM_ADMIN","SUPER_ADMIN","TENANT_ADMIN","OWNER","APPROVER","RECEPTION","SECURITY"]);
        requireTenantScope_(role,actorTenant,targetTenant); return visitorTransition_(d,a==="CHECK_IN"?"CHECKED_IN":"CHECKED_OUT");
      default: return out_({status:"error",message:"Unsupported action"});
    }
  }catch(err){console.error(err&&err.stack||err);return out_({status:"error",message:"Request could not be processed."});}
}
function trusted_(candidate){
  const expected=PropertiesService.getScriptProperties().getProperty("AI_GROWTH_OS_BRIDGE_SECRET");
  if(!expected||!candidate||String(expected).length!==String(candidate).length)return false;
  let diff=0,a=String(expected),b=String(candidate);
  for(let i=0;i<a.length;i++)diff|=a.charCodeAt(i)^b.charCodeAt(i);
  return diff===0;
}
function role_(value){return clean_(value,40).toUpperCase().replace(/[ -]+/g,"_");}
function requireRole_(actual,allowed){if(allowed.indexOf(actual)<0)throw new Error("Forbidden: role is not permitted for this action");}
function requireTenantScope_(role,actorTenant,targetTenant){if(role!=="PLATFORM_ADMIN"&&role!=="SUPER_ADMIN"&&(!actorTenant||!targetTenant||actorTenant!==targetTenant))throw new Error("Tenant access denied");}
function ensureSheet_(ss,name,headers){
  let s=ss.getSheetByName(name);if(!s)s=ss.insertSheet(name);
  if(s.getLastRow()===0){s.getRange(1,1,1,headers.length).setValues([headers]);s.setFrozenRows(1);}
  else{
    const old=s.getRange(1,1,1,Math.max(s.getLastColumn(),headers.length)).getDisplayValues()[0];
    headers.forEach(h=>{if(old.indexOf(h)<0)s.getRange(1,s.getLastColumn()+1).setValue(h);});
    s.setFrozenRows(1);
  }
  const width=s.getLastColumn();s.getRange(1,1,1,width).setFontWeight("bold").setBackground("#1e293b").setFontColor("#fff");
  return s;
}
function registerTenant_(d){
  const name=cell_(d.name,160);if(!name)return out_({status:"error",message:"Tenant name required."});
  const ss=SpreadsheetApp.getActiveSpreadsheet(),s=ensureSheet_(ss,TENANTS,["Tenant Code","Organization Name","Category","Assigned Role","Contact Person","Email ID","Mobile Number","Reception Clearance","Staff Details","App URL","Spreadsheet URL","Registered At","Status"]);
  const code=cell_(d.code,80)||"TNT-"+Utilities.getUuid().slice(0,8).toUpperCase();
  if(findRow_(s,1,code))return out_({status:"error",message:"Tenant code already exists."});
  s.appendRow([code,name,clean_(d.category,100)||"Organization",clean_(d.role,100)||"Tenant Administrator",clean_(d.contactName,160)||"Admin",clean_(d.adminEmail,200).toLowerCase(),clean_(d.contactMobile,40),d.hasReception===true?"ENABLED":"DISABLED",Array.isArray(d.receptionStaffNames)?d.receptionStaffNames.map(x=>clean_(x,100)).join(", "):"",clean_(d.pwaAppDownloadUrl,500)||"https://ai-growth-os-web.onrender.com",clean_(d.monthlySpreadsheetUrl,500)||ss.getUrl(),new Date().toISOString(),"ACTIVE"]);
  return out_({status:"success",tenantCode:code,message:"Tenant registered."});
}
function getTenants_(){
  const v=ensureSheet_(SpreadsheetApp.getActiveSpreadsheet(),TENANTS,["Tenant Code","Organization Name","Category","Assigned Role","Contact Person","Email ID","Mobile Number","Reception Clearance","Staff Details","App URL","Spreadsheet URL","Registered At","Status"]).getDataRange().getDisplayValues(),a=[];
  for(let i=1;i<v.length;i++){let r=v[i];if(r[0]||r[1])a.push({code:r[0],name:r[1],category:r[2],role:r[3],contactName:r[4],adminEmail:r[5],contactMobile:r[6],receptionStatus:r[7],status:r[12]||"ACTIVE"});}
  return out_({status:"success",tenants:a});
}
function getUsers_(tenantFilter){
  const filter=clean_(tenantFilter,100);
  const v=ensureSheet_(SpreadsheetApp.getActiveSpreadsheet(),USERS,["Email","Name","Role","Designation","Status","Tenant ID","RegisteredAt"]).getDataRange().getDisplayValues(),a=[];
  for(let i=1;i<v.length;i++){let r=v[i];if(r[0]&&(!filter||r[5]===filter))a.push({email:r[0],name:r[1],role:r[2],designation:r[3],status:r[4],tenantId:r[5]});}
  return out_({status:"success",users:a});
}
function addUser_(email,name,role,designation,tenantId){
  email=clean_(email,200).toLowerCase();tenantId=clean_(tenantId,80);role=role_(role);
  if(!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)||!tenantId)return out_({status:"error",message:"Valid email and tenant ID required."});
  if(["OWNER","PLATFORM_ADMIN","TENANT_ADMIN","ADMIN","APPROVER","RECEPTION","SECURITY","STAFF"].indexOf(role)<0)return out_({status:"error",message:"Invalid role."});
  const s=ensureSheet_(SpreadsheetApp.getActiveSpreadsheet(),USERS,["Email","Name","Role","Designation","Status","Tenant ID","RegisteredAt"]),r=findRow_(s,1,email),row=[email,clean_(name,160)||email.split("@")[0],role,clean_(designation,120)||"Staff","ACTIVE",tenantId,new Date().toISOString()];
  if(r)s.getRange(r,1,1,row.length).setValues([row]);else s.appendRow(row);
  return out_({status:"success",message:r?"User updated.":"User added."});
}
function visitorRequest_(d){
  const tenant=clean_(d.tenantId||d.tenantCode,100),name=clean_(d.visitorName,160),mobile=clean_(d.visitorMobile||d.mobile,40);
  if(!tenant||!name||!mobile)return out_({status:"error",message:"Tenant, visitor name and mobile required."});
  if(!tenantExists_(tenant))return out_({status:"error",message:"Unknown or inactive tenant."});
  const s=ensureSheet_(SpreadsheetApp.getActiveSpreadsheet(),LOGS,["Date","Ticket ID","Tenant Name","Visitor Name","Mobile","Purpose","Target Destination","Vehicle Number","Status","Approver Name","QR Token","Snapshot Link","Tenant ID","Updated At","Updated By","Notes"]);
  const ticket="TKT-"+Utilities.getUuid().slice(0,12).toUpperCase(),now=new Date().toISOString();
  const row={"Date":cell_(d.date,80)||now,"Ticket ID":ticket,"Tenant Name":tenantName_(tenant),"Visitor Name":cell_(name,160),"Mobile":cell_(mobile,40),"Purpose":cell_(d.purpose,500),"Target Destination":cell_(d.targetDestination,200),"Vehicle Number":cell_(d.vehicleNumber,40),"Status":"PENDING","Approver Name":"","QR Token":"","Snapshot Link":snapshot_(d.imageBase64,d.vehicleNumber||name),"Tenant ID":tenant,"Updated At":now,"Updated By":"AI_GROWTH_OS","Notes":"Awaiting staff approval"};
  const headers=s.getRange(1,1,1,s.getLastColumn()).getDisplayValues()[0];s.appendRow(headers.map(h=>Object.prototype.hasOwnProperty.call(row,h)?row[h]:""));
  return out_({status:"success",ticketId:ticket,statusLabel:"PENDING",message:"Request submitted for staff approval."});
}
function listVisitors_(d){
  const tenant=clean_(d.tenantId,100);if(!tenant)return out_({status:"error",message:"Tenant ID required."});
  const v=ensureSheet_(SpreadsheetApp.getActiveSpreadsheet(),LOGS,["Date","Ticket ID","Tenant Name","Visitor Name","Mobile","Purpose","Target Destination","Vehicle Number","Status","Approver Name","QR Token","Snapshot Link","Tenant ID","Updated At","Updated By","Notes"]).getDataRange().getDisplayValues(),h=v[0]||[],tc=h.indexOf("Tenant ID"),a=[];
  for(let i=1;i<v.length;i++){if(tc>=0&&v[i][tc]===tenant){let o={};h.forEach((x,j)=>o[x]=v[i][j]);a.push(o);}}
  return out_({status:"success",visitors:a});
}
function visitorTransition_(d,next){
  const tenant=clean_(d.tenantId||d.tenantCode,100),ticket=clean_(d.ticketId,100),actor=clean_(d.actorEmail||d.actorName,200);
  if(!tenant||!ticket||!actor)return out_({status:"error",message:"Tenant, ticket and authenticated actor required."});
  const s=ensureSheet_(SpreadsheetApp.getActiveSpreadsheet(),LOGS,["Date","Ticket ID","Tenant Name","Visitor Name","Mobile","Purpose","Target Destination","Vehicle Number","Status","Approver Name","QR Token","Snapshot Link","Tenant ID","Updated At","Updated By","Notes"]),v=s.getDataRange().getDisplayValues(),h=v[0],ti=h.indexOf("Ticket ID"),te=h.indexOf("Tenant ID"),st=h.indexOf("Status");
  for(let i=1;i<v.length;i++){
    if(v[i][ti]!==ticket||v[i][te]!==tenant)continue;
    const old=v[i][st],allowed=next==="APPROVED"||next==="REJECTED"?["PENDING"]:next==="CHECKED_IN"?["APPROVED"]:["CHECKED_IN"];
    if(allowed.indexOf(old)<0)return out_({status:"error",message:"Invalid status transition: "+old+" → "+next});
    s.getRange(i+1,st+1).setValue(next);
    let qrToken="";
    if(next==="APPROVED"){
      const qi=h.indexOf("QR Token");
      if(qi>=0){
        qrToken=String(v[i][qi]||"").trim();
        if(!qrToken){qrToken=Utilities.getUuid().replace(/-/g,"")+Utilities.getUuid().replace(/-/g,"");s.getRange(i+1,qi+1).setValue(qrToken);}
      }
    }
    ["Updated At","Updated By"].forEach(k=>{let c=h.indexOf(k);if(c>=0)s.getRange(i+1,c+1).setValue(k==="Updated At"?new Date().toISOString():actor);});
    if(next==="APPROVED"&&h.indexOf("Approver Name")>=0)s.getRange(i+1,h.indexOf("Approver Name")+1).setValue(actor);
    return out_({status:"success",ticketId:ticket,visitorStatus:next,qrToken:qrToken});
  }
  return out_({status:"error",message:"Ticket not found for this tenant."});
}
function verifyVisitorToken_(d){
  const tenant=clean_(d.tenantId||d.tenantCode,100),token=clean_(d.token||d.qrToken,256);
  if(!tenant||!token)return out_({status:"error",message:"Tenant and QR token required."});
  const s=ensureSheet_(SpreadsheetApp.getActiveSpreadsheet(),LOGS,["Date","Ticket ID","Tenant Name","Visitor Name","Mobile","Purpose","Target Destination","Vehicle Number","Status","Approver Name","QR Token","Snapshot Link","Tenant ID","Updated At","Updated By","Notes"]);
  const v=s.getDataRange().getDisplayValues(),h=v[0]||[],idx={};
  ["Ticket ID","Tenant ID","Visitor Name","Mobile","Purpose","Target Destination","Vehicle Number","Status","QR Token"].forEach(k=>idx[k]=h.indexOf(k));
  for(let i=1;i<v.length;i++){
    if(v[i][idx["Tenant ID"]]!==tenant||v[i][idx["QR Token"]]!==token)continue;
    const status=String(v[i][idx["Status"]]||"").toUpperCase();
    if(status!=="APPROVED")return out_({status:"success",valid:false,message:"Pass is not approved or has already been used."});
    return out_({status:"success",valid:true,pass:{ticketId:v[i][idx["Ticket ID"]],tenantId:tenant,visitorName:v[i][idx["Visitor Name"]],visitorMobile:v[i][idx["Mobile"]],purpose:v[i][idx["Purpose"]],destination:v[i][idx["Target Destination"]],vehicleNumber:v[i][idx["Vehicle Number"]],status:status,qrToken:token}});
  }
  return out_({status:"success",valid:false,message:"Invalid QR token for this tenant."});
}
function tenantExists_(id){
  const v=ensureSheet_(SpreadsheetApp.getActiveSpreadsheet(),TENANTS,["Tenant Code","Organization Name","Category","Assigned Role","Contact Person","Email ID","Mobile Number","Reception Clearance","Staff Details","App URL","Spreadsheet URL","Registered At","Status"]).getDataRange().getDisplayValues();
  return v.slice(1).some(r=>(r[0]===id||r[1]===id)&&String(r[12]||"ACTIVE").toUpperCase()==="ACTIVE");
}
function tenantName_(id){
  const v=SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TENANTS).getDataRange().getDisplayValues();
  for(let i=1;i<v.length;i++)if(v[i][0]===id)return v[i][1];return id;
}
function snapshot_(base64,name){
  if(!base64||String(base64).length<50)return "";
  try{const raw=String(base64).replace(/^data:image\/[a-zA-Z]+;base64,/,""),bytes=Utilities.base64Decode(raw);if(bytes.length>5*1024*1024)return "";
    const file=folder_(DRIVE_FOLDER).createFile(Utilities.newBlob(bytes,"image/jpeg",clean_(name,80).replace(/[^a-zA-Z0-9_-]/g,"_")+"_"+Date.now()+".jpg"));return file.getUrl();
  }catch(e){console.error("Snapshot save failed: "+e);return "";}
}
function folder_(name){const f=DriveApp.getFoldersByName(name);return f.hasNext()?f.next():DriveApp.createFolder(name);}
function findRow_(s,col,value){const n=s.getLastRow();if(n<2)return 0;const a=s.getRange(2,col,n-1,1).getDisplayValues();for(let i=0;i<a.length;i++)if(String(a[i][0]).trim()===String(value).trim())return i+2;return 0;}
function clean_(v,n){return String(v==null?"":v).replace(/[\u0000-\u001F\u007F]/g," ").trim().slice(0,n||500);}
function cell_(v,n){const x=clean_(v,n);return /^[=+@\-]/.test(x)?"'"+x:x;}
function out_(o){return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);}

// Spreadsheet-editor-only convenience menu actions; web requests still require bridge auth.
function promptCreateTenant(){
  const ui=SpreadsheetApp.getUi(),n=ui.prompt("Create Tenant","Organization name:",ui.ButtonSet.OK_CANCEL);
  if(n.getSelectedButton()!==ui.Button.OK||!n.getResponseText().trim())return;
  const c=ui.prompt("Category","School, IT Park, Mall, Hospital, etc.",ui.ButtonSet.OK_CANCEL),e=ui.prompt("Admin Email","Administrator email:",ui.ButtonSet.OK_CANCEL),m=ui.prompt("Mobile","Contact mobile:",ui.ButtonSet.OK_CANCEL);
  const r=registerTenant_({name:n.getResponseText(),category:c.getResponseText(),adminEmail:e.getResponseText(),contactMobile:m.getResponseText(),hasReception:true});
  ui.alert(r.getContent());
}
function promptAddUser(){
  const ui=SpreadsheetApp.getUi(),e=ui.prompt("Add Staff","Email:",ui.ButtonSet.OK_CANCEL);if(e.getSelectedButton()!==ui.Button.OK)return;
  const n=ui.prompt("Name","Full name:",ui.ButtonSet.OK_CANCEL),r=ui.prompt("Role","SECURITY, RECEPTION, APPROVER, TENANT_ADMIN:",ui.ButtonSet.OK_CANCEL),t=ui.prompt("Tenant ID","Exact tenant code:",ui.ButtonSet.OK_CANCEL);
  const result=addUser_(e.getResponseText(),n.getResponseText(),r.getResponseText(),"Staff",t.getResponseText());ui.alert(result.getContent());
}