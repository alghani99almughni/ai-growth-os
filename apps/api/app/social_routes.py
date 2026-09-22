from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session
import json
import httpx

from .db import SessionLocal
from .models_integrations import TenantIntegration
from .integrations import decrypt_channel_config, encrypt_channel_config
from .config import settings

router = APIRouter(prefix="/api/v1", tags=["social"])

security = HTTPBearer(auto_error=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _user(credentials, db):
    from .main import get_current_user
    return get_current_user(credentials=credentials, db=db)

def _tenant(user, tenant_id):
    if user.tenant_id != tenant_id:
        raise HTTPException(403, "Tenant access denied")

def _row(db, tenant_id, key):
    return db.scalar(select(TenantIntegration).where(
        TenantIntegration.tenant_id == tenant_id,
        TenantIntegration.integration_key == key,
        TenantIntegration.status == "connected",
    ))

def _cfg(row):
    if not row or not row.config_encrypted:
        raise HTTPException(400, "Integration is not connected")
    try:
        return decrypt_channel_config(
            row.config_encrypted,
            settings.integration_credential_encryption_key or settings.whatsapp_credential_encryption_key,
        )
    except Exception:
        raise HTTPException(500, "Integration credentials could not be decrypted")

async def _request(method, url, **kwargs):
    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.request(method, url, **kwargs)
        if r.status_code >= 400:
            try:
                detail = r.json()
            except Exception:
                detail = r.text[:1000]
            raise HTTPException(r.status_code, f"Provider API error: {detail}")
        return r

async def _google_access(row, cfg):
    access = cfg.get("access_token")
    refresh = cfg.get("refresh_token")
    if not access:
        raise HTTPException(400, "Google access token is missing")
    # Refresh when we have a refresh token. This avoids relying on short-lived access tokens.
    if refresh:
        r = await _request("POST", "https://oauth2.googleapis.com/token", data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh,
        })
        data = r.json()
        access = data.get("access_token") or access
        cfg["access_token"] = access
        row.config_encrypted = encrypt_channel_config(
            cfg, settings.integration_credential_encryption_key or settings.whatsapp_credential_encryption_key
        )
        row.updated_at = __import__("datetime").datetime.utcnow()
    return access

@router.get("/tenants/{tenant_id}/social/{key}/health")
async def social_health(tenant_id: str, key: str, credentials: HTTPAuthorizationCredentials=Depends(security), db: Session=Depends(get_db)):
    user = _user(credentials, db); _tenant(user, tenant_id)
    if key not in {"facebook","instagram","meta_ads","youtube","google_business"}:
        raise HTTPException(400, "Unsupported social integration")
    row = _row(db, tenant_id, key)
    if not row:
        return {"key": key, "connected": False}
    try:
        cfg = _cfg(row)
        if key in {"facebook","instagram","meta_ads"}:
            token = cfg["access_token"]
            r = await _request("GET", f"https://graph.facebook.com/{settings.meta_graph_api_version}/me",
                                params={"fields":"id,name","access_token":token})
            return {"key":key,"connected":True,"provider":"meta","account_id":row.account_id,"account_name":row.account_name,"provider_account":r.json()}
        access = await _google_access(row, cfg)
        if key == "youtube":
            r = await _request("GET","https://www.googleapis.com/youtube/v3/channels",
                               params={"part":"snippet,statistics","mine":"true"},
                               headers={"Authorization":"Bearer "+access})
        else:
            r = await _request("GET","https://mybusinessaccountmanagement.googleapis.com/v1/accounts",
                               headers={"Authorization":"Bearer "+access})
        db.commit()
        return {"key":key,"connected":True,"provider":"google","account_id":row.account_id,"account_name":row.account_name,"provider_account":r.json()}
    except HTTPException:
        return {"key":key,"connected":False,"account_id":row.account_id,"account_name":row.account_name}

@router.post("/tenants/{tenant_id}/social/facebook/publish")
async def publish_facebook(tenant_id: str, message: str=Form(...), link: str|None=Form(None),
                           credentials: HTTPAuthorizationCredentials=Depends(security), db: Session=Depends(get_db)):
    user=_user(credentials,db); _tenant(user,tenant_id)
    row=_row(db,tenant_id,"facebook"); cfg=_cfg(row)
    if not row.account_id: raise HTTPException(400,"Facebook Page is not selected")
    params={"message":message,"access_token":cfg["access_token"]}
    if link: params["link"]=link
    r=await _request("POST",f"https://graph.facebook.com/{settings.meta_graph_api_version}/{row.account_id}/feed",data=params)
    return {"platform":"facebook","status":"published","result":r.json()}

@router.post("/tenants/{tenant_id}/social/instagram/publish")
async def publish_instagram(tenant_id: str, image_url: str=Form(...), caption: str=Form(""),
                            credentials: HTTPAuthorizationCredentials=Depends(security), db: Session=Depends(get_db)):
    user=_user(credentials,db); _tenant(user,tenant_id)
    row=_row(db,tenant_id,"instagram"); cfg=_cfg(row)
    if not row.account_id: raise HTTPException(400,"Instagram professional account is not connected")
    base=f"https://graph.facebook.com/{settings.meta_graph_api_version}/{row.account_id}"
    container=(await _request("POST",base+"/media",data={"image_url":image_url,"caption":caption,"access_token":cfg["access_token"]})).json()
    creation_id=container.get("id")
    if not creation_id: raise HTTPException(502,"Instagram did not return a media container")
    published=(await _request("POST",base+"/media_publish",data={"creation_id":creation_id,"access_token":cfg["access_token"]})).json()
    return {"platform":"instagram","status":"published","creation_id":creation_id,"result":published}

@router.get("/tenants/{tenant_id}/social/meta_ads/insights")
async def meta_ads_insights(tenant_id: str, date_from: str, date_to: str,
                            credentials: HTTPAuthorizationCredentials=Depends(security), db: Session=Depends(get_db)):
    user=_user(credentials,db); _tenant(user,tenant_id)
    row=_row(db,tenant_id,"meta_ads"); cfg=_cfg(row)
    if not row.account_id: raise HTTPException(400,"Meta Ads account is not connected")
    account=row.account_id if str(row.account_id).startswith("act_") else "act_"+str(row.account_id)
    params={"access_token":cfg["access_token"],"fields":"campaign_name,impressions,reach,clicks,spend,ctr,cpc,cpm,actions",
            "time_range":json.dumps({"since":date_from,"until":date_to}),"level":"campaign"}
    r=await _request("GET",f"https://graph.facebook.com/{settings.meta_graph_api_version}/{account}/insights",params=params)
    return {"platform":"meta_ads","date_from":date_from,"date_to":date_to,"items":r.json().get("data",[])}

@router.get("/tenants/{tenant_id}/social/google_business/locations")
async def google_locations(tenant_id: str, credentials: HTTPAuthorizationCredentials=Depends(security), db: Session=Depends(get_db)):
    user=_user(credentials,db); _tenant(user,tenant_id)
    row=_row(db,tenant_id,"google_business"); cfg=_cfg(row); access=await _google_access(row,cfg)
    account=row.account_id or ""
    if not account.startswith("accounts/"): raise HTTPException(400,"Google Business account is not connected")
    r=await _request("GET",f"https://mybusinessbusinessinformation.googleapis.com/v1/{account}/locations",
                      params={"readMask":"name,title,storeCode,metadata"},
                      headers={"Authorization":"Bearer "+access})
    db.commit()
    return {"items":r.json().get("locations",[])}

@router.post("/tenants/{tenant_id}/social/google_business/post")
async def google_business_post(tenant_id: str, location_name: str=Form(...), summary: str=Form(...),
                               topic_type: str=Form("STANDARD"), action_type: str|None=Form(None),
                               action_url: str|None=Form(None), image_url: str|None=Form(None),
                               credentials: HTTPAuthorizationCredentials=Depends(security), db: Session=Depends(get_db)):
    user=_user(credentials,db); _tenant(user,tenant_id)
    row=_row(db,tenant_id,"google_business"); cfg=_cfg(row); access=await _google_access(row,cfg)
    if not location_name.startswith("locations/"):
        account=row.account_id or ""
        if account.startswith("accounts/"): location_name=account+"/"+location_name.lstrip("/")
        else: raise HTTPException(400,"Use a Google Business location resource name")
    body={"languageCode":"en-US","summary":summary,"topicType":topic_type}
    if action_type and action_url:
        body["callToAction"]={"actionType":action_type,"url":action_url}
    if image_url:
        body["media"]=[{"mediaFormat":"PHOTO","sourceUrl":image_url}]
    r=await _request("POST",f"https://mybusiness.googleapis.com/v4/{location_name}/localPosts",
                      headers={"Authorization":"Bearer "+access,"Content-Type":"application/json"},json=body)
    db.commit()
    return {"platform":"google_business","status":"published","result":r.json()}

@router.get("/tenants/{tenant_id}/social/google_business/posts")
async def google_business_posts(tenant_id: str, location_name: str,
                                credentials: HTTPAuthorizationCredentials=Depends(security), db: Session=Depends(get_db)):
    user=_user(credentials,db); _tenant(user,tenant_id)
    row=_row(db,tenant_id,"google_business"); cfg=_cfg(row); access=await _google_access(row,cfg)
    r=await _request("GET",f"https://mybusiness.googleapis.com/v4/{location_name}/localPosts",
                      headers={"Authorization":"Bearer "+access})
    db.commit()
    return {"items":r.json().get("localPosts",[])}

@router.post("/tenants/{tenant_id}/social/youtube/upload")
async def youtube_upload(tenant_id: str, title: str=Form(...), description: str=Form(""),
                         privacy_status: str=Form("private"), category_id: str=Form("22"),
                         video: UploadFile=File(...),
                         credentials: HTTPAuthorizationCredentials=Depends(security), db: Session=Depends(get_db)):
    user=_user(credentials,db); _tenant(user,tenant_id)
    row=_row(db,tenant_id,"youtube"); cfg=_cfg(row); access=await _google_access(row,cfg)
    if privacy_status not in {"private","unlisted","public"}: raise HTTPException(400,"Invalid privacy status")
    if not (video.content_type or "").startswith("video/"): raise HTTPException(400,"Only video files are accepted")
    meta={"snippet":{"title":title,"description":description,"categoryId":category_id},
          "status":{"privacyStatus":privacy_status}}
    # YouTube requires a resumable upload session for reliable large uploads.
    data=await video.read()
    if len(data)>256*1024*1024*1024: raise HTTPException(413,"Video exceeds YouTube's 256GB limit")
    init=await _request("POST","https://www.googleapis.com/upload/youtube/v3/videos",
                        params={"uploadType":"resumable","part":"snippet,status"},
                        headers={"Authorization":"Bearer "+access,"Content-Type":"application/json",
                                 "X-Upload-Content-Length":str(len(data)),
                                 "X-Upload-Content-Type":video.content_type},
                        json=meta)
    upload_url=init.headers.get("location")
    if not upload_url: raise HTTPException(502,"YouTube did not return an upload session")
    async with httpx.AsyncClient(timeout=300) as client:
        up=await client.put(upload_url,headers={"Authorization":"Bearer "+access,"Content-Type":video.content_type,
                                                 "Content-Length":str(len(data))},content=data)
        if up.status_code>=400:
            raise HTTPException(up.status_code,up.text[:1000])
    db.commit()
    return {"platform":"youtube","status":"uploaded","result":up.json()}

@router.post("/tenants/{tenant_id}/social/{key}/disconnect")
async def social_disconnect(tenant_id: str, key: str, credentials: HTTPAuthorizationCredentials=Depends(security), db: Session=Depends(get_db)):
    user=_user(credentials,db); _tenant(user,tenant_id)
    if key not in {"facebook","instagram","meta_ads","youtube","google_business","meta_business"}:
        raise HTTPException(400,"Unsupported social integration")
    row=db.scalar(select(TenantIntegration).where(TenantIntegration.tenant_id==tenant_id,TenantIntegration.integration_key==key))
    if not row: return {"key":key,"status":"disconnected"}
    cfg={}
    try: cfg=_cfg(row)
    except HTTPException: pass
    try:
        if key in {"facebook","instagram","meta_ads","meta_business"} and cfg.get("access_token"):
            await _request("DELETE",f"https://graph.facebook.com/{settings.meta_graph_api_version}/me/permissions",
                           params={"access_token":cfg["access_token"]})
        elif key in {"youtube","google_business"} and cfg.get("access_token"):
            await _request("POST","https://oauth2.googleapis.com/revoke",
                           params={"token":cfg["access_token"]})
    except Exception:
        # Local credential removal still proceeds if provider-side revocation is unavailable.
        pass
    row.status="disconnected"; row.config_encrypted=""; row.account_name=None; row.account_id=None; row.metadata_json="{}"
    db.commit()
    return {"key":key,"status":"disconnected"}
