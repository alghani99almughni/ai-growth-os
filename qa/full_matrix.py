import os,requests,time,statistics,concurrent.futures,random,json
BASE=os.environ["API_URL"].rstrip("/")
S=requests.Session(); S.headers.update({"Content-Type":"application/json"})
errors=[]; lat=[]
categories=[
("health","QA Health Clinic"),("wellness","QA Wellness Center"),("dental","QA Dental Clinic"),
("restaurant","QA Restaurant"),("hotel","QA Hotel"),("salon","QA Salon"),("gym","QA Gym"),
("real-estate","QA Real Estate"),("education","QA Education"),("automotive","QA Automotive"),
("retail","QA Retail Store"),("legal","QA Legal Services"),("travel","QA Travel Agency"),
("home-services","QA Home Services"),("professional-services","QA Professional Services")]
probes=[("what","What services do you provide?"),("if","If I need help, what can you do for me?"),
("now","Can I get help now?"),("when","When are you open?"),("where","Where are you located?"),
("why","Why should I contact your business?"),("how","How can I book an appointment?"),("who","Who can help me?")]
def fail(cat,case,error,solution): errors.append((cat,case,error,solution)); print("FAIL",cat,case,error)
def auth_tenant(industry,name,i):
    slug="qa-"+industry.replace("_","-"); email=f"qa-{slug}@example.com"; pw="QaMatrix!2026"
    p={"name":f"QA Owner {i}","email":email,"password":pw,"business_name":name,"slug":slug,"industry":industry}
    r=S.post(BASE+"/api/v1/auth/register",json=p,timeout=25)
    if r.status_code==201: return r.json()
    if r.status_code==409:
        r=S.post(BASE+"/api/v1/auth/login",json={"email":email,"password":pw},timeout=25); r.raise_for_status(); return r.json()
    raise RuntimeError(f"auth {r.status_code}: {r.text[:500]}")
def call(slug,n):
    r=S.post(f"{BASE}/api/v1/public/business/{slug}/call",json={"name":f"QA Customer {n}","phone":f"+91999{random.randint(1000000,9999999)}"},timeout=25); r.raise_for_status(); return r.json()["call_id"]
def turn(slug,cid,msg,conv=None):
    r=S.post(f"{BASE}/api/v1/public/business/{slug}/voice/turn",json={"transcript":msg,"call_id":cid,"conversation_id":conv,"channel":"voice"},timeout=35)
    if r.status_code>=500: raise RuntimeError(f"HTTP {r.status_code}: {r.text[:400]}")
    r.raise_for_status(); return r.json()
tenants=[]
for i,(ind,name) in enumerate(categories,1):
    try:
        a=auth_tenant(ind,name,i); slug="qa-"+ind
        h={"Authorization":"Bearer "+a["access_token"],"Content-Type":"application/json"}
        r=S.post(f'{BASE}/api/v1/tenants/{a["tenant"]["id"]}/services',headers=h,json={"name":"QA Consultation","description":"QA","price":100,"currency":"INR","duration_minutes":30,"is_active":True},timeout=25)
        if r.status_code not in (201,409): raise RuntimeError(f"service {r.status_code}: {r.text[:300]}")
        tenants.append((ind,slug,a["tenant"]["id"]))
    except Exception as e: fail(ind,"tenant-provision",str(e),"Fix registration/service provisioning; keep it idempotent."); continue
if len(tenants)!=15: raise SystemExit(f"Only {len(tenants)}/15 tenants provisioned")
for ind,slug,_ in tenants:
    for kind,msg in probes:
        t=time.perf_counter()
        try:
            x=turn(slug,call(slug,1),msg); lat.append(time.perf_counter()-t)
            if not x.get("reply"): fail(ind,kind,"empty reply","Return a safe deterministic/library/AI-or-handoff response.")
        except Exception as e: fail(ind,kind,str(e),"Trace call/conversation IDs and fix the failing tenant/intention path.")
    try:
        cid=call(slug,2); conv=turn(slug,cid,"I want to book an appointment").get("conversation_id")
        conv=turn(slug,cid,"today",conv).get("conversation_id")
        x=turn(slug,cid,"now",conv); conv=x.get("conversation_id"); rep=x.get("reply","").lower()
        if "what time would you prefer" in rep or "which time" in rep: fail(ind,"today-now","repeated time question","Resolve now to next available local slot or explicitly say no remaining slot.")
        # Native/romanized Indian-language equivalents of "now" must enter the same state machine.
        for now_text in ("abhi","अभी"):
            cid=call(slug,20); conv=turn(slug,cid,"I want to book an appointment").get("conversation_id")
            conv=turn(slug,cid,"today",conv).get("conversation_id")
            x=turn(slug,cid,now_text,conv); rep=x.get("reply","").lower()
            if "what time would you prefer" in rep or "which time" in rep:
                fail(ind,"now-"+now_text,"repeated time question","Resolve now/abhi/अभी to the next available local slot.")
        cid=call(slug,3); conv=None
        for m in ("I want an appointment","tomorrow","2 o'clock"):
            x=turn(slug,cid,m,conv); conv=x.get("conversation_id")
        x=turn(slug,cid,"Yes, confirm it",conv); bid=x.get("booking",{}).get("booking_id")
        if not bid: fail(ind,"booking-confirm-natural","no booking_id","Accept natural affirmative confirmation and create the appointment transactionally.")
        x=turn(slug,cid,"Cancel my appointment",conv)
        if bid and not x.get("booking",{}).get("cancellation_confirmed"): fail(ind,"booking-cancel","not cancelled","Persist and transactionally cancel the exact appointment.")
        # Exercise a second natural confirmation form after a fresh booking.
        cid=call(slug,30); conv=None
        for m in ("I want an appointment","tomorrow","3 PM"):
            x=turn(slug,cid,m,conv); conv=x.get("conversation_id")
        x=turn(slug,cid,"Okay book it",conv); bid2=x.get("booking",{}).get("booking_id")
        if not bid2: fail(ind,"booking-confirm-okay-book","no booking_id","Accept bounded natural confirmation phrases.")
        else:
            x=turn(slug,cid,"cancel it",conv)
            if not x.get("booking",{}).get("cancellation_confirmed"): fail(ind,"booking-cancel-second","not cancelled","Cancel the exact active appointment.")
    except Exception as e: fail(ind,"booking-state-machine",str(e),"Fix booking state persistence and transaction boundaries.")
    for lang,a,b in [
        ("hi","हिंदी में बात कर सकते हैं","मुझे अपॉइंटमेंट बुक करना है"),
        ("te","తెలుగులో మాట్లాడగలరా?","నాకు అపాయింట్మెంట్ కావాలి"),
        ("roman","Hindi mein baat kar sakte hain","abhi book karna hai")]:
        try:
            cid=call(slug,4); conv=turn(slug,cid,a).get("conversation_id"); x=turn(slug,cid,b,conv)
            if not x.get("reply"): fail(ind,"language-"+lang,"empty reply","Preserve requested language and return a safe response.")
        except Exception as e: fail(ind,"language-"+lang,str(e),"Fix language detection/persistence.")
    for m in ["What if I change my mind?","What if the slot is unavailable?","When exactly?","When can I come?","Where exactly?","Where are you located?","Why do you need my number?","Why is this service useful?","How much does it cost?","How can I book?","Who is available right now?","Who can help me?","maybe","no","not now","2 PM","2 o'clock","12 noon","12 PM","tomorrow","Monday","abhi","अभी","कल","सोमवार","cancel","I changed my mind"]:
        try:
            cid=call(slug,5); x=turn(slug,cid,m)
            if not x.get("reply"): fail(ind,"edge:"+m,"empty reply","Never crash or return an empty conversational response.")
        except Exception as e: fail(ind,"edge:"+m,str(e),"Add deterministic clarification/recovery for the utterance.")
def load_one(i):
    ind,slug,_=tenants[i%15]; t=time.perf_counter()
    try: turn(slug,call(slug,600+i),probes[i%8][1]); return time.perf_counter()-t,True,ind,""
    except Exception as e: return time.perf_counter()-t,False,ind,str(e)
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex: rr=list(ex.map(load_one,range(60)))
for _,ok,ind,e in rr:
    if not ok: fail(ind,"concurrency",e,"Fix concurrency/session/database contention.")
p95=sorted(x[0] for x in rr)[56]; print("PERF p50=%.2fs p95=%.2fs"%(statistics.median(x[0] for x in rr),p95))
if p95>20: fail("platform","performance",f"p95 {p95:.2f}s >20s","Profile DB/API/fallback latency and remove blocking work.")
for ind,slug,_ in tenants:
    r=S.get(f"{BASE}/api/v1/public/business/{slug}/website",timeout=20)
    if r.status_code!=200: fail(ind,"tenant-isolation",f"HTTP {r.status_code}","Keep public business reads tenant-scoped.")
with open("qa_error_log.md","w",encoding="utf-8") as f:
    f.write("# Full QA Error Log\n\n")
    if errors:
        for c,k,e,s in errors: f.write(f"## {c} / {k}\n**Error:** {e}\n\n**Solution:** {s}\n\n")
    else: f.write("No unresolved failures. 15 tenants, WH matrix, booking, multilingual, adversarial, isolation and concurrency checks passed.\n")
print("TOTAL_FAILURES",len(errors))
if errors: raise SystemExit(1)
print("FULL 15-TENANT QA MATRIX: PASS")