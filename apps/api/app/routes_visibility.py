"""Tenant-scoped AEO/GEO profile, provider visibility, and audit APIs.

AI provider results are recorded as bounded observations, not universal rankings.
Website fetching remains disabled until its connection-time SSRF controls are verified.
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
            raise HTTPException(422, f"Website homepage exceeds the {max_bytes}-byte audit limit.")
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
    # Defense in depth: the frontend button is also disabled, but direct API calls
    # must not trigger outbound requests until connection-time SSRF protection is verified.
    raise HTTPException(503, "Website audit is temporarily disabled pending security hardening.")
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


# ── AI-answer visibility checks (separate from the deterministic website audit) ──
from .models_visibility import VisibilityCheckRun, VisibilityObservation
from .visibility_providers import PROVIDER_ORDER, run_provider, observation_match, _contains_brand_name
from .config import settings as visibility_settings
from pydantic import BaseModel, Field

class VisibilityCheckPayload(BaseModel):
    providers: list[str] = Field(default_factory=lambda: list(PROVIDER_ORDER), min_length=1, max_length=4)

def _provider_config(provider: str, tenant_id: str, db: Session):
    values = {
        "gemini": (visibility_settings.gemini_api_key, visibility_settings.gemini_model, "gemini"),
        "perplexity": (visibility_settings.perplexity_api_key, visibility_settings.perplexity_model, "perplexity"),
        "grok": (visibility_settings.grok_api_key, visibility_settings.grok_model, "grok"),
        "claude": (visibility_settings.anthropic_api_key, visibility_settings.anthropic_model, "anthropic"),
    }
    env_key, env_model, integration_key = values.get(provider, ("", "", ""))
    if integration_key:
        row = db.scalar(select(TenantIntegration).where(
            TenantIntegration.tenant_id == tenant_id,
            TenantIntegration.integration_key == integration_key,
            TenantIntegration.status == "connected"))
        if row and row.config_encrypted:
            try:
                stored_config = decrypt_channel_config(row.config_encrypted, (
                    visibility_settings.integration_credential_encryption_key
                    or visibility_settings.whatsapp_credential_encryption_key))
                if stored_config.get("api_key"):
                    return stored_config.get("api_key"), stored_config.get("model") or env_model
            except Exception:
                pass
    return env_key, env_model

@router.post("/checks/{query_id}", status_code=201)
async def run_visibility_checks(tenant_id: str, query_id: str, payload: VisibilityCheckPayload,
                                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Run a saved query against configured providers and persist evidence per provider."""
    _authorize(user, tenant_id)
    query = db.scalar(select(VisibilityQuery).where(
        VisibilityQuery.id == query_id, VisibilityQuery.tenant_id == tenant_id,
        VisibilityQuery.is_active.is_(True)))
    if not query:
        raise HTTPException(404, "Active visibility query not found")
    brand = db.scalar(select(VisibilityBrand).where(
        VisibilityBrand.tenant_id == tenant_id).order_by(VisibilityBrand.created_at.asc()))
    if not brand:
        raise HTTPException(400, "Save your brand profile before running visibility checks")
    providers = list(dict.fromkeys(p.lower() for p in payload.providers))
    if any(p not in PROVIDER_ORDER for p in providers):
        raise HTTPException(422, "Supported providers: gemini, perplexity, grok, claude")
    results = []
    for provider in providers:
        api_key, model = _provider_config(provider, tenant_id, db)
        run = VisibilityCheckRun(tenant_id=tenant_id, query_id=query.id, provider=provider,
                                 measurement_method="search_grounded" if provider in ("gemini", "perplexity") else "model_sampled",
                                 status="running", started_at=datetime.utcnow())
        db.add(run)
        db.commit()
        db.refresh(run)
        try:
            prompt = (
                f"Answer this customer question for locale {query.locale}: {query.query_text}\n"
                f"Evaluate businesses fairly and use web search where the provider supports it. "
                f"Do not assume facts not supported by sources. Business being tracked: {brand.name} "
                f"(website: {brand.primary_domain}). Return a concise answer with citations when available."
            )
            observed = await run_provider(provider, api_key, model, prompt)
            match = observation_match(observed["answer"], brand.name, brand.primary_domain, observed["citations"])
            answer_lower = observed["answer"].casefold()
            competitors = db.scalars(select(VisibilityCompetitor).where(
                VisibilityCompetitor.tenant_id == tenant_id)).all()
            competitor_mentions = [item.name for item in competitors if _contains_brand_name(observed["answer"], item.name)]
            mentioned_names = ([brand.name] if match["brand_mentioned"] else []) + competitor_mentions
            cited_urls = [item["url"] for item in observed["citations"]]
            db.add(VisibilityObservation(
                tenant_id=tenant_id, run_id=run.id,
                brand_mentioned=match["brand_mentioned"],
                mentioned_names_json=json.dumps(mentioned_names),
                cited_urls_json=json.dumps(cited_urls),
                answer_excerpt=observed["answer"][:4000],
                evidence_quality=match["evidence_quality"],
                observed_at=datetime.utcnow()))
            run.status = "completed"
            run.error_code = None
            results.append({"run_id": run.id, "provider": provider, "model": observed["model"],
                            "status": "completed", "measurement_method": observed["method"],
                            "brand_mentioned": match["brand_mentioned"], "website_cited": match["website_cited"],
                            "competitor_mentions": competitor_mentions,
                            "citations": observed["citations"], "answer_excerpt": observed["answer"][:4000],
                            "evidence_quality": match["evidence_quality"]})
        except Exception as exc:
            run.status = "failed"
            run.error_code = "provider_not_configured" if "not configured" in str(exc).lower() else "provider_request_failed"
            results.append({"run_id": run.id, "provider": provider, "status": "failed",
                            "error_code": run.error_code,
                            "message": "Provider API key/model is not configured." if run.error_code == "provider_not_configured" else "Provider request failed; verify API access, quota and model configuration."})
        run.completed_at = datetime.utcnow()
        db.commit()
    return {"query_id": query.id, "query_text": query.query_text, "brand": brand.name,
            "results": results,
            "note": "Results are observations for these exact provider queries, not universal rankings or a guarantee of what every consumer sees."}

@router.get("/checks")
def list_visibility_checks(tenant_id: str, limit: int = 50,
                           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _authorize(user, tenant_id)
    rows = db.scalars(select(VisibilityCheckRun).where(
        VisibilityCheckRun.tenant_id == tenant_id
    ).order_by(VisibilityCheckRun.created_at.desc()).limit(min(max(limit, 1), 100))).all()
    items = []
    for row in rows:
        observation = db.scalar(select(VisibilityObservation).where(
            VisibilityObservation.run_id == row.id,
            VisibilityObservation.tenant_id == tenant_id))
        items.append({"run_id": row.id, "query_id": row.query_id, "provider": row.provider,
                      "measurement_method": row.measurement_method, "status": row.status,
                      "error_code": row.error_code,
                      "brand_mentioned": observation.brand_mentioned if observation else None,
                      "mentioned_names": json.loads(observation.mentioned_names_json or "[]") if observation else [],
                      "cited_urls": json.loads(observation.cited_urls_json or "[]") if observation else [],
                      "answer_excerpt": observation.answer_excerpt if observation else "",
                      "evidence_quality": observation.evidence_quality if observation else None,
                      "created_at": row.created_at.isoformat() if row.created_at else None,
                      "completed_at": row.completed_at.isoformat() if row.completed_at else None})
    return {"items": items}


# ── Official Google Search Console performance data (separate from Gemini tests) ──
from datetime import date, timedelta
from urllib.parse import quote
from .models_integrations import TenantIntegration
from .integrations import decrypt_channel_config

class SearchConsolePayload(BaseModel):
    site_url: str = Field(min_length=4, max_length=2048)
    start_date: date
    end_date: date
    row_limit: int = Field(default=100, ge=1, le=1000)

@router.post("/google-search-console/performance")
async def google_search_console_performance(tenant_id: str, payload: SearchConsolePayload,
                                           user: User = Depends(get_current_user),
                                           db: Session = Depends(get_db)):
    """Fetch official Search Console query/page metrics from a tenant's connected OAuth integration."""
    import httpx
    _authorize(user, tenant_id)
    if payload.start_date > payload.end_date:
        raise HTTPException(422, "Start date must be on or before end date")
    if (payload.end_date - payload.start_date).days > 500:
        raise HTTPException(422, "Choose a date range of 500 days or less")
    integration = db.scalar(select(TenantIntegration).where(
        TenantIntegration.tenant_id == tenant_id,
        TenantIntegration.integration_key == "google_search_console",
        TenantIntegration.status == "connected"))
    if not integration or not integration.config_encrypted:
        raise HTTPException(400, "Connect Google Search Console OAuth in Integrations before requesting official data")
    if not visibility_settings.google_client_id or not visibility_settings.google_client_secret:
        raise HTTPException(503, "Google OAuth client configuration is missing on the server")
    try:
        cfg = decrypt_channel_config(
            integration.config_encrypted,
            visibility_settings.integration_credential_encryption_key or visibility_settings.whatsapp_credential_encryption_key)
    except Exception:
        raise HTTPException(503, "Google Search Console connection could not be read safely")
    refresh_token = cfg.get("refresh_token")
    if not refresh_token:
        raise HTTPException(400, "The connected Google account has no refresh token; reconnect it with Search Console access")
    async with httpx.AsyncClient(timeout=httpx.Timeout(25.0, connect=8.0), follow_redirects=False) as client:
        token_response = await client.post("https://oauth2.googleapis.com/token", data={
            "client_id": visibility_settings.google_client_id,
            "client_secret": visibility_settings.google_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        })
        if token_response.status_code >= 400:
            raise HTTPException(502, "Google OAuth refresh failed; reconnect the Google account")
        access_token = token_response.json().get("access_token")
        if not access_token:
            raise HTTPException(502, "Google OAuth did not return an access token")
        endpoint = "https://searchconsole.googleapis.com/webmasters/v3/sites/" + quote(payload.site_url, safe="") + "/searchAnalytics/query"
        response = await client.post(endpoint, headers={"Authorization": "Bearer " + access_token},
            json={"startDate": payload.start_date.isoformat(), "endDate": payload.end_date.isoformat(),
                  "dimensions": ["query", "page"], "rowLimit": payload.row_limit})
    if response.status_code >= 400:
        raise HTTPException(502, "Google Search Console query failed; verify the selected property and account permissions")
    data = response.json()
    return {"source": "google_search_console", "site_url": payload.site_url,
            "start_date": payload.start_date.isoformat(), "end_date": payload.end_date.isoformat(),
            "rows": data.get("rows", []), "row_count": len(data.get("rows", [])),
            "note": "These are official Search Console query/page performance metrics. They are not a standalone Gemini visibility score and do not guarantee reporting of AI Overviews or AI Mode separately."}
