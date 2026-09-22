"""Semantic Knowledge Library.

Embeddings are cached on approved tenant knowledge items. Retrieval happens
before generation, so repeated/known questions consume no generation tokens.
"""
from __future__ import annotations
import hashlib, json, math, re
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models_growth import KnowledgeItem
from .config import settings

EMBED_MODEL="gemini-embedding-001"
_CACHE={}

def _cosine(a,b):
    if not a or not b or len(a)!=len(b): return 0.0
    dot=sum(x*y for x,y in zip(a,b)); na=math.sqrt(sum(x*x for x in a)); nb=math.sqrt(sum(y*y for y in b))
    return dot/(na*nb) if na and nb else 0.0

def _fallback_vector(text, dims=256):
    # Deterministic zero-dependency semantic fallback; provider embeddings supersede it.
    v=[0.0]*dims
    for token in re.findall(r"[\w\u00c0-\uffff]{2,}",text.casefold(),re.UNICODE):
        h=int(hashlib.sha256(token.encode()).hexdigest()[:8],16)%dims
        v[h]+=1.0
    n=math.sqrt(sum(x*x for x in v)) or 1.0
    return [x/n for x in v]

async def embed_text(text:str):
    key=hashlib.sha256(text.encode("utf-8")).hexdigest()
    if key in _CACHE: return _CACHE[key],"cache"
    if settings.gemini_api_key:
        import httpx
        url=f"https://generativelanguage.googleapis.com/v1beta/models/{EMBED_MODEL}:embedContent"
        body={"model":"models/"+EMBED_MODEL,"content":{"parts":[{"text":text}]},"output_dimensionality":768}
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                r=await client.post(url,headers={"x-goog-api-key":settings.gemini_api_key,"Content-Type":"application/json"},json=body)
                r.raise_for_status()
                values=(r.json().get("embedding") or {}).get("values") or []
                if values:
                    _CACHE[key]=values
                    return values,"gemini"
        except Exception:
            pass
    values=_fallback_vector(text)
    _CACHE[key]=values
    return values,"local"

async def semantic_match(db:Session,tenant_id:str,message:str,language:str,threshold:float=0.72):
    rows=db.scalars(select(KnowledgeItem).where(
        KnowledgeItem.tenant_id==tenant_id,
        KnowledgeItem.is_active==True,
        KnowledgeItem.approval_status.in_(["approved","system"])
    )).all()
    if not rows: return None
    query_vec,_=await embed_text(message)
    best=None; best_score=0.0
    for row in rows:
        text=(row.title or "")+"\n"+(row.content or "")
        if row.embedding_json:
            try: vec=json.loads(row.embedding_json)
            except Exception: vec=None
        else: vec=None
        if not vec:
            vec,_=await embed_text(text)
            row.embedding_json=json.dumps(vec,separators=(",",":"))
            row.embedding_model=EMBED_MODEL
        score=_cosine(query_vec,vec)
        if row.language==language: score+=0.04
        if score>best_score: best_score,best=score,row
    if best and best_score>=threshold:
        best.usage_count=(best.usage_count or 0)+1
        from datetime import datetime
        best.last_used_at=datetime.utcnow()
        db.commit()
        return {"content":best.content,"item_id":best.id,"score":round(best_score,4),"provider":"semantic_library"}
    return None
