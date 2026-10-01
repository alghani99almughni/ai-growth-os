"""Wire website_templates.py into main.py.

Changes:
1. Import website_templates helpers at the top.
2. Replace the DEFAULT_WEBSITE_CONTENT-only merge in public_website()
   with industry-aware template + tenant override.
3. Include tenant features in the response so the site can render
   conditionally.
4. Extend the tenant website editor endpoints to preserve template
   defaults so the tenant doesn't lose their industry styling.
"""

import pathlib

path = pathlib.Path("main.py")
text = path.read_text(encoding="utf-8")

if "website_templates" in text:
    print("SKIP: already patched")
    raise SystemExit(0)

# ---------------------------------------------------------------------------
# 1. Add import after the last existing ".from .*" import
# ---------------------------------------------------------------------------

import_anchor = "from .tenant_policy import tenant_policy, capability_enabled, policy_context\n"

new_import = (
    "from .tenant_policy import tenant_policy, capability_enabled, policy_context\n"
    "from .website_templates import get_template as _get_site_template\n"
    "from .website_templates import merge_with_tenant as _merge_site_content\n"
)

if import_anchor not in text:
    print("ERROR: import anchor not found")
    raise SystemExit(1)

text = text.replace(import_anchor, new_import, 1)
print("Imported website_templates")

# ---------------------------------------------------------------------------
# 2. Replace public_website with template-aware version
# ---------------------------------------------------------------------------

old_public_website = '''@app.get("/api/v1/public/business/{slug}/website")
def public_website(slug:str,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower(),Tenant.status=="active"))
    if not t: raise HTTPException(404,"Business not found")
    row=db.scalar(select(TenantSetting).where(TenantSetting.tenant_id==t.id,TenantSetting.key=="website_content"))
    try: content={**DEFAULT_WEBSITE_CONTENT,**(json.loads(row.value_json) if row else {})}
    except Exception: content=dict(DEFAULT_WEBSITE_CONTENT)
    voice_row=db.scalar(select(TenantSetting).where(TenantSetting.tenant_id==t.id,TenantSetting.key=="agent_voice"))
    agent_voice={"gender":"female"}
    if voice_row:
        try:
            parsed=json.loads(voice_row.value_json)
            agent_voice=parsed if isinstance(parsed,dict) else {"gender":str(parsed).lower()}
        except Exception: pass
    if agent_voice.get("gender") not in ("female","male"): agent_voice["gender"]="female"
    return {"business":{"id":t.id,"name":t.name,"slug":t.slug,"phone":t.phone,"whatsapp_number":t.whatsapp_number,"address":t.address,"description":t.description,"agent_gender":agent_voice["gender"]},"content":content}'''

new_public_website = '''@app.get("/api/v1/public/business/{slug}/website")
def public_website(slug:str,db:Session=Depends(get_db)):
    t=db.scalar(select(Tenant).where(Tenant.slug==slug.lower(),Tenant.status=="active"))
    if not t: raise HTTPException(404,"Business not found")
    row=db.scalar(select(TenantSetting).where(TenantSetting.tenant_id==t.id,TenantSetting.key=="website_content"))
    tenant_overrides={}
    if row:
        try: tenant_overrides=json.loads(row.value_json) or {}
        except Exception: tenant_overrides={}
    template=_get_site_template(t.industry or "")
    content=_merge_site_content(template, tenant_overrides)
    # tenant name substitution for {name} placeholders
    for k,v in list(content.items()):
        if isinstance(v,str):
            content[k]=v.replace("{name}", t.name or "")
    voice_row=db.scalar(select(TenantSetting).where(TenantSetting.tenant_id==t.id,TenantSetting.key=="agent_voice"))
    agent_voice={"gender":"female"}
    if voice_row:
        try:
            parsed=json.loads(voice_row.value_json)
            agent_voice=parsed if isinstance(parsed,dict) else {"gender":str(parsed).lower()}
        except Exception: pass
    if agent_voice.get("gender") not in ("female","male"): agent_voice["gender"]="female"
    return {
        "business":{
            "id":t.id,"name":t.name,"slug":t.slug,"phone":t.phone,
            "whatsapp_number":t.whatsapp_number,"address":t.address,
            "description":t.description,"industry":t.industry,
            "agent_gender":agent_voice["gender"],
            "features":_feature_config(db, t.id),
        },
        "content":content,
    }'''

if old_public_website not in text:
    print("WARNING: public_website body changed - patching more carefully")
    # Fallback: find the function and rewrite from def to next @app
    start = text.find('@app.get("/api/v1/public/business/{slug}/website")')
    if start > 0:
        next_marker = text.find('\n@app.', start + 10)
        if next_marker > 0:
            text = text[:start] + new_public_website + text[next_marker:]
            print("Patched public_website (fallback method)")
        else:
            print("ERROR: could not find next @app decorator")
            raise SystemExit(1)
    else:
        print("ERROR: public_website decorator not found")
        raise SystemExit(1)
else:
    text = text.replace(old_public_website, new_public_website, 1)
    print("Replaced public_website")

# ---------------------------------------------------------------------------
# 3. Update the tenant editor GET to also return template defaults
#    (so the editor shows industry defaults when tenant hasn't overridden)
# ---------------------------------------------------------------------------

old_tenant_website = '''@app.get("/api/v1/tenants/{tenant_id}/website")
def tenant_website(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    row=db.scalar(select(TenantSetting).where(TenantSetting.tenant_id==tenant_id,TenantSetting.key=="website_content"))
    try: return {**DEFAULT_WEBSITE_CONTENT,**(json.loads(row.value_json) if row else {})}
    except Exception: return dict(DEFAULT_WEBSITE_CONTENT)'''

new_tenant_website = '''@app.get("/api/v1/tenants/{tenant_id}/website")
def tenant_website(tenant_id,user=Depends(get_current_user),db:Session=Depends(get_db)):
    require_tenant(user,tenant_id)
    row=db.scalar(select(TenantSetting).where(TenantSetting.tenant_id==tenant_id,TenantSetting.key=="website_content"))
    tenant_overrides={}
    if row:
        try: tenant_overrides=json.loads(row.value_json) or {}
        except Exception: tenant_overrides={}
    tenant=db.get(Tenant, tenant_id)
    template=_get_site_template((tenant.industry if tenant else "") or "")
    content=_merge_site_content(template, tenant_overrides)
    # Include tenant name substitution
    for k,v in list(content.items()):
        if isinstance(v,str):
            content[k]=v.replace("{name}", (tenant.name if tenant else "") or "")
    return content'''

if old_tenant_website not in text:
    print("WARNING: tenant_website body changed - skipping editor GET")
else:
    text = text.replace(old_tenant_website, new_tenant_website, 1)
    print("Replaced tenant_website (editor GET)")

path.write_text(text, encoding="utf-8")
print("Done. New size:", len(text), "bytes")
print("website_templates references:", text.count("_get_site_template") + text.count("_merge_site_content"))