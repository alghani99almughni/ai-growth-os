"""Add feature-flag enforcement to public endpoints in main.py.

Blueprint: 'Feature flags must be enforced in the backend, not only hidden
in the UI.'

Adds feature checks to 9 public endpoints that currently lack them.
All checks use the existing _feature_config helper and return HTTP 403
when the feature is disabled.
"""

import pathlib

path = pathlib.Path("main.py")
text = path.read_text(encoding="utf-8")

if "# === ENDPOINT FEATURE GATES ===" in text:
    print("SKIP: already patched")
    raise SystemExit(0)

# ---------------------------------------------------------------------------
# Insertions: (find, replace)
# Each insertion places a feature check right after the "business not found"
# guard in each endpoint.
# ---------------------------------------------------------------------------

edits = []

# 1. public_appointment -> bookings
edits.append((
    '''def public_appointment(slug,payload:AppointmentCreate,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    if not payload.phone and not payload.customer_id: raise HTTPException(400,"Phone is required for a public booking")''',
    '''def public_appointment(slug,payload:AppointmentCreate,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    if not _feature_config(db,t.id).get("bookings",True): raise HTTPException(403,"Bookings are not available for this business")
    if not payload.phone and not payload.customer_id: raise HTTPException(400,"Phone is required for a public booking")'''
))

# 2. create_feedback -> feedback
edits.append((
    '''def create_feedback(slug,payload:FeedbackCreate,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    f=Feedback(tenant_id=t.id,**payload.model_dump()); db.add(f); db.commit()''',
    '''def create_feedback(slug,payload:FeedbackCreate,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    if not _feature_config(db,t.id).get("feedback",True): raise HTTPException(403,"Feedback is not available for this business")
    f=Feedback(tenant_id=t.id,**payload.model_dump()); db.add(f); db.commit()'''
))

# 3. start_public_call -> ai_voice
edits.append((
    '''def start_public_call(slug:str,payload:PublicCallStartRequest,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    customer=None''',
    '''def start_public_call(slug:str,payload:PublicCallStartRequest,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    if not _feature_config(db,t.id).get("ai_voice",True): raise HTTPException(403,"Voice calling is not available for this business")
    customer=None'''
))

# 4. public_voice_ice -> ai_voice
edits.append((
    '''def public_voice_ice(slug:str, db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    servers=[{"urls":"stun:stun.l.google.com:19302"}]''',
    '''def public_voice_ice(slug:str, db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    if not _feature_config(db,t.id).get("ai_voice",True): raise HTTPException(403,"Voice calling is not available for this business")
    servers=[{"urls":"stun:stun.l.google.com:19302"}]'''
))

# 5. public_voice_turn -> ai_voice
edits.append((
    '''def public_voice_turn(slug:str,payload:PublicVoiceTurnRequest,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    result=await generate_reply(db,t.id,payload.transcript,payload.conversation_id,payload.channel)''',
    '''def public_voice_turn(slug:str,payload:PublicVoiceTurnRequest,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    if not _feature_config(db,t.id).get("ai_voice",True): raise HTTPException(403,"Voice calling is not available for this business")
    result=await generate_reply(db,t.id,payload.transcript,payload.conversation_id,payload.channel)'''
))

# 6. public_handoff_start -> human_handoff
edits.append((
    '''    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    call=db.scalar(select(CallRecord).where(
        CallRecord.id==call_id, CallRecord.tenant_id==t.id, CallRecord.source=="pwa_voice"
    ))
    if not call: raise HTTPException(404,"Call not found")
    age=(datetime.utcnow()-call.started_at).total_seconds() if call.started_at else 999999''',
    '''    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    if not _feature_config(db,t.id).get("human_handoff",True): raise HTTPException(403,"Human handoff is not available for this business")
    call=db.scalar(select(CallRecord).where(
        CallRecord.id==call_id, CallRecord.tenant_id==t.id, CallRecord.source=="pwa_voice"
    ))
    if not call: raise HTTPException(404,"Call not found")
    age=(datetime.utcnow()-call.started_at).total_seconds() if call.started_at else 999999'''
))

# 7. public_handoff_status -> human_handoff
edits.append((
    '''def public_handoff_status(slug:str, call_id:str, db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    call=db.scalar(select(CallRecord).where(CallRecord.id==call_id,CallRecord.tenant_id==t.id))''',
    '''def public_handoff_status(slug:str, call_id:str, db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    if not _feature_config(db,t.id).get("human_handoff",True): raise HTTPException(403,"Human handoff is not available for this business")
    call=db.scalar(select(CallRecord).where(CallRecord.id==call_id,CallRecord.tenant_id==t.id))'''
))

# 8. public_menu -> digital_menu
edits.append((
    '''def public_menu(slug,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    return _public_menu(db,t)''',
    '''def public_menu(slug,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower()))
    if not t: raise HTTPException(404,"Business not found")
    if not _feature_config(db,t.id).get("digital_menu",True): raise HTTPException(403,"Menu is not available for this business")
    return _public_menu(db,t)'''
))

# 9. public_chat -> ai_chat
edits.append((
    '''def public_chat(payload:ChatRequest,db:Session=Depends(get_db)):
    t=db.get(Tenant,payload.tenant_id)
    if not t: raise HTTPException(404,"Business not found")
    if not payload.phone or not payload.name:''',
    '''def public_chat(payload:ChatRequest,db:Session=Depends(get_db)):
    t=db.get(Tenant,payload.tenant_id)
    if not t: raise HTTPException(404,"Business not found")
    if not _feature_config(db,t.id).get("ai_chat",True): raise HTTPException(403,"AI chat is not available for this business")
    if not payload.phone or not payload.name:'''
))

# ---------------------------------------------------------------------------
# Apply all edits.
# ---------------------------------------------------------------------------

applied = 0
skipped = 0

for old, new in edits:
    if old in text:
        text = text.replace(old, new, 1)
        applied += 1
        # Show a short identifier of what we patched
        first_line = old.split("\n")[0][:60]
        print(f"  PATCHED: {first_line}")
    else:
        skipped += 1
        first_line = old.split("\n")[0][:60]
        print(f"  SKIP (not found): {first_line}")

# Add a marker for idempotency
if "# === ENDPOINT FEATURE GATES ===" not in text:
    text = text.rstrip() + "\n\n# === ENDPOINT FEATURE GATES ===\n"

path.write_text(text, encoding="utf-8")
print(f"\nDone. {applied} patched, {skipped} skipped.")
print("New size:", len(text), "bytes")