"""Tenant-scoped AEO/GEO profile and query APIs.

This first slice intentionally stores configuration and questions only. It does not
pretend to run live AI search checks; provider adapters and SSRF-safe auditing are
separate follow-up work.
"""
import re, json, socket, ipaddress
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import SessionLocal
from .models import User
from .models_visibility import VisibilityBrand, VisibilityCompetitor, VisibilityQuery, VisibilityAudit, VisibilityAuditFinding

# Imported by main.py at the end of module initialization to avoid an import cycle.
from .main import get_current_user, get_db, require_tenant

router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/visibility", tags=["AEO/GEO Visibility"])

def _authorize(user: User, tenant_id: str):
    require_tenant(user, tenant_id)
    if user.role not in ("platform_admin", "super_admin") and user.tenant_id != tenant_id:
        raise HTTPException(403, "Tenant access denied")

def _domain(value: str) -> str:
    value = value.strip()
    candidate = value if "://" in value else "https://" + value
    parts = urlsplit(candidate)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise HTTPException(422, "Enter a valid website domain, for example https://example.com")
    if parts.username or parts.password or parts.port not in (None, 80, 443):
        raise HTTPException(422, "Website URL credentials and custom ports are not supported")
    host = parts.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost") or "." not in host:
        raise HTTPException(422, "Enter a public internet domain")
    # Reject IP literals at profile-entry time. The audit accepts hostnames only,
    # then independently checks every DNS answer is globally routable.
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise HTTPException(422, "Enter a public website domain, not an IP address")
    if not re.fullmatch(r"[a-z0-9.-]+", host) or ".." in host:
        raise HTTPException(422, "Enter a valid public internet domain")
    labels = host.split(".")
    if any(not label or label.startswith("-") or label.endswith("-") or len(label) > 63 for label in labels):
        raise HTTPException(422, "Enter a valid public internet domain")
    if len(host) > 253:
        raise HTTPException(422, "Enter a valid public internet domain")
    return host

class BrandPayload(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    primary_domain: str = Field(min_length=3, max_length=253)
    description: str = Field(default="", max_length=4000)
    locale: str = Field(default="en", min_length=2, max_length=20)

class CompetitorPayload(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    domain: str = Field(min_length=3, max_length=253)
    notes: str = Field(default="", max_length=2000)

class QueryPayload(BaseModel):
    query_text: str = Field(min_length=3, max_length=500)
    intent: str = Field(default="informational", pattern="^(informational|local|comparison|transactional|navigational)$")
    locale: str = Field(default="en", min_length=2, max_length=20)
    topic: str = Field(default="", max_length=120)
    is_active: bool = True

def _brand_out(row):
    return {"id": row.id, "tenant_id": row.tenant_id, "name": row.name,
            "primary_domain": row.primary_domain, "description": row.description,
            "locale": row.locale, "created_at": row.created_at.isoformat() if row.created_at else None}

@router.get("/brand")
def get_brand(tenant_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _authorize(user, tenant_id)
    row = db.scalar(select(VisibilityBrand).where(VisibilityBrand.tenant_id == tenant_id).order_by(VisibilityBrand.created_at.asc()))
    return {"brand": _brand_out(row) if row else None}

@router.put("/brand")
def put_brand(tenant_id: str, payload: BrandPayload, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _authorize(user, tenant_id)
    row = db.scalar(select(VisibilityBrand).where(VisibilityBrand.tenant_id == tenant_id).order_by(VisibilityBrand.created_at.asc()))
    if row is None:
        row = VisibilityBrand(tenant_id=tenant_id, name=payload.name.strip(), primary_domain=_domain(payload.primary_domain))
        db.add(row)
    row.name = payload.name.strip()
    row.primary_domain = _domain(payload.primary_domain)
    row.description = payload.description.strip()
    row.locale = payload.locale.strip()
    db.commit()
    db.refresh(row)
    return {"brand": _brand_out(row)}

@router.get("/competitors")
def list_competitors(tenant_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _authorize(user, tenant_id)
    rows = db.scalars(select(VisibilityCompetitor).where(VisibilityCompetitor.tenant_id == tenant_id).order_by(VisibilityCompetitor.created_at.desc()).limit(100)).all()
    return {"items": [{"id": r.id, "name": r.name, "domain": r.domain, "notes": r.notes, "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]}

@router.post("/competitors", status_code=201)
def add_competitor(tenant_id: str, payload: CompetitorPayload, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _authorize(user, tenant_id)
    row = VisibilityCompetitor(tenant_id=tenant_id, name=payload.name.strip(), domain=_domain(payload.domain), notes=payload.notes.strip())
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "name": row.name, "domain": row.domain, "notes": row.notes}

@router.delete("/competitors/{competitor_id}")
def delete_competitor(tenant_id: str, competitor_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _authorize(user, tenant_id)
    row = db.scalar(select(VisibilityCompetitor).where(VisibilityCompetitor.id == competitor_id, VisibilityCompetitor.tenant_id == tenant_id))
    if not row:
        raise HTTPException(404, "Competitor not found")
    db.delete(row); db.commit()
    return {"deleted": True}

@router.get("/queries")
def list_queries(tenant_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _authorize(user, tenant_id)
    rows = db.scalars(select(VisibilityQuery).where(VisibilityQuery.tenant_id == tenant_id).order_by(VisibilityQuery.created_at.desc()).limit(200)).all()
    return {"items": [{"id": r.id, "query_text": r.query_text, "intent": r.intent, "locale": r.locale, "topic": r.topic, "is_active": r.is_active, "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]}

@router.post("/queries", status_code=201)
def add_query(tenant_id: str, payload: QueryPayload, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _authorize(user, tenant_id)
    row = VisibilityQuery(tenant_id=tenant_id, query_text=payload.query_text.strip(), intent=payload.intent, locale=payload.locale.strip(), topic=payload.topic.strip(), is_active=payload.is_active)
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "query_text": row.query_text, "intent": row.intent, "locale": row.locale, "topic": row.topic, "is_active": row.is_active}


class _SEOParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts = []
        self.in_title = False
        self.description = ""
        self.canonical = ""
        self.robots = ""
        self.h1_count = 0
        self.structured_data = False
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag.lower() == "title": self.in_title = True
        if tag.lower() == "h1": self.h1_count += 1
        if tag.lower() == "meta" and a.get("name", "").lower() == "description": self.description = a.get("content", "").strip()
        if tag.lower() == "meta" and a.get("name", "").lower() == "robots": self.robots = a.get("content", "").strip()
        if tag.lower() == "link" and "canonical" in a.get("rel", "").lower().split(): self.canonical = a.get("href", "").strip()
        if tag.lower() == "script" and a.get("type", "").lower() == "application/ld+json": self.structured_data = True
    def handle_endtag(self, tag):
        if tag.lower() == "title": self.in_title = False
    def handle_data(self, data):
        if self.in_title: self.title_parts.append(data.strip())

def _read_bounded_body(response, max_bytes: int = 500000) -> bytes:
    """Read a response body only up to the configured limit; reject rather than audit a partial page."""
    chunks = []
    total = 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(422, "Website homepage is larger than the 500 KB audit limit.")
        chunks.append(chunk)
    return b"".join(chunks)


def _validated_public_url(value: str) -> str:
    host = _domain(value)
    parts = urlsplit(value if "://" in value else "https://" + value)
    try:
        addresses = {item[4][0].split("%")[0] for item in socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80), type=socket.SOCK_STREAM)}
    except (socket.gaierror, OSError):
        raise HTTPException(422, "Website domain could not be resolved")
    if not addresses:
        raise HTTPException(422, "Website domain could not be resolved")
    for address in addresses:
        try: ip = ipaddress.ip_address(address)
        except ValueError: raise HTTPException(422, "Website domain resolved to an invalid address")
        if not ip.is_global:
            raise HTTPException(422, "Private or reserved network addresses are not allowed")
    path = parts.path or "/"
    return urlunsplit((parts.scheme, host, path, parts.query, ""))

@router.post("/audits", status_code=201)
def run_website_audit(tenant_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Run a small, bounded first-page audit. No redirects, scripts, or arbitrary page crawling."""
    import httpx
    _authorize(user, tenant_id)
    brand = db.scalar(select(VisibilityBrand).where(VisibilityBrand.tenant_id == tenant_id).order_by(VisibilityBrand.created_at.asc()))
    if not brand:
        raise HTTPException(400, "Save your brand profile before starting a website audit")
    url = _validated_public_url("https://" + brand.primary_domain)
    try:
        with httpx.Client(timeout=httpx.Timeout(8.0, connect=3.0), follow_redirects=False,
                          headers={"User-Agent": "AIGrowthOS-VisibilityAudit/1.0"}) as client:
            with client.stream("GET", url) as response:
                status_code = response.status_code
                content_type = response.headers.get("content-type", "")
                if status_code < 300 and "text/html" in content_type.lower():
                    body_bytes = _read_bounded_body(response)
                    body = body_bytes.decode(response.encoding or "utf-8", errors="replace")
                else:
                    body = ""
    except httpx.TimeoutException:
        raise HTTPException(422, "Website request timed out. Try again later.")
    except httpx.HTTPError:
        raise HTTPException(422, "Website could not be reached safely.")
    if 300 <= status_code < 400:
        findings = [{"category":"crawlability","severity":"warning","title":"Website redirects",
                     "recommendation":"Review the redirect destination and canonical domain. Redirect following is disabled for safety.",
                     "evidence":str(status_code)}]
        body = ""
    elif status_code >= 400:
        findings = [{"category":"availability","severity":"high","title":"Website returned an HTTP error",
                     "recommendation":"Check that the public website is available to visitors and crawlers.",
                     "evidence":str(status_code)}]
        body = ""
    elif "text/html" not in content_type.lower():
        findings = [{"category":"content","severity":"warning","title":"Homepage is not HTML",
                     "recommendation":"Confirm that the brand URL points to the public website homepage.",
                     "evidence":content_type or "unknown"}]
        body = ""
    else:
        parser = _SEOParser()
        parser.feed(body)
        title = " ".join(parser.title_parts).strip()
        description = parser.description
        findings = []
        if not title:
            findings.append({"category":"metadata","severity":"high","title":"Missing page title","recommendation":"Add a unique, descriptive HTML title for the homepage.","evidence":""})
        elif len(title) > 60:
            findings.append({"category":"metadata","severity":"low","title":"Page title may be too long","recommendation":"Review whether the title can be shortened while keeping the main service and brand.","evidence":title[:240]})
        if not description:
            findings.append({"category":"metadata","severity":"medium","title":"Missing meta description","recommendation":"Add a concise, unique meta description that explains the business and its main value.","evidence":""})
        if parser.h1_count == 0:
            findings.append({"category":"content","severity":"medium","title":"No H1 heading detected","recommendation":"Add a clear main heading that describes the page purpose.","evidence":""})
        elif parser.h1_count > 1:
            findings.append({"category":"content","severity":"low","title":"Multiple H1 headings detected","recommendation":"Review the heading hierarchy so the primary page topic is clear.","evidence":str(parser.h1_count)})
        if not parser.canonical:
            findings.append({"category":"technical","severity":"low","title":"No canonical link detected","recommendation":"Consider adding a canonical URL when the page has duplicate or alternate URL variants.","evidence":""})
        if not parser.structured_data:
            findings.append({"category":"structured_data","severity":"medium","title":"No JSON-LD structured data detected","recommendation":"Consider adding appropriate Organization or LocalBusiness structured data when accurate for the business.","evidence":""})
        if "noindex" in parser.robots.lower():
            findings.append({"category":"indexing","severity":"high","title":"Robots meta tag includes noindex","recommendation":"Confirm whether search engines should be allowed to index this public page.","evidence":parser.robots[:200]})
        if not findings:
            findings.append({"category":"metadata","severity":"info","title":"No basic homepage metadata issues detected","recommendation":"Continue with deeper content, sitemap, internal-link and structured-data validation.","evidence":"First-page checks only"})
    record = VisibilityAudit(tenant_id=tenant_id, target_url=url, status="completed" if status_code < 400 else "partial",
                             http_status=status_code, pages_checked=1,
                             summary_json=json.dumps({"finding_count":len(findings),"content_type":content_type[:120],
                                                      "title_detected": bool(body and "<title" in body.lower()),
                                                      "scope":"single public homepage; basic HTML checks only"}))
    db.add(record); db.flush()
    for item in findings:
        db.add(VisibilityAuditFinding(tenant_id=tenant_id,audit_id=record.id,category=item["category"],severity=item["severity"],
                                      title=item["title"],recommendation=item["recommendation"],evidence=item["evidence"][:500]))
    db.commit(); db.refresh(record)
    return {"id":record.id,"status":record.status,"target_url":record.target_url,"http_status":record.http_status,
            "pages_checked":1,"findings":findings,"scope":"Single homepage only. No AI visibility score or live AI answer check is included.",
            "created_at":record.created_at.isoformat() if record.created_at else None}

@router.get("/audits")
def list_website_audits(tenant_id: str, limit: int = 20, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _authorize(user, tenant_id)
    rows = db.scalars(select(VisibilityAudit).where(VisibilityAudit.tenant_id == tenant_id)
                      .order_by(VisibilityAudit.created_at.desc()).limit(min(max(limit, 1), 50))).all()
    return {"items":[{"id":r.id,"target_url":r.target_url,"status":r.status,"http_status":r.http_status,
                      "pages_checked":r.pages_checked,"summary":json.loads(r.summary_json or "{}"),
                      "created_at":r.created_at.isoformat() if r.created_at else None} for r in rows]}

@router.get("/audits/{audit_id}")
def get_website_audit(tenant_id: str, audit_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _authorize(user, tenant_id)
    record = db.scalar(select(VisibilityAudit).where(VisibilityAudit.id == audit_id, VisibilityAudit.tenant_id == tenant_id))
    if not record: raise HTTPException(404, "Audit not found")
    rows = db.scalars(select(VisibilityAuditFinding).where(VisibilityAuditFinding.audit_id == record.id,
                            VisibilityAuditFinding.tenant_id == tenant_id).order_by(VisibilityAuditFinding.created_at.asc())).all()
    return {"id":record.id,"target_url":record.target_url,"status":record.status,"http_status":record.http_status,
            "pages_checked":record.pages_checked,"summary":json.loads(record.summary_json or "{}"),
            "findings":[{"category":r.category,"severity":r.severity,"title":r.title,"recommendation":r.recommendation,"evidence":r.evidence}
                        for r in rows],"created_at":record.created_at.isoformat() if record.created_at else None}
