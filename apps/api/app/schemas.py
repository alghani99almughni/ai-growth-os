from pydantic import BaseModel, Field
from typing import Optional

class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    industry: str = Field(min_length=2, max_length=80)

class TenantOut(TenantCreate):
    id: str

class CustomerCreate(BaseModel):
    tenant_id: str
    phone: str = Field(min_length=5, max_length=32)
    name: Optional[str] = Field(default=None, max_length=160)
    whatsapp_opt_in: bool = False

class LeadCreate(BaseModel):
    tenant_id: str
    customer_id: Optional[str] = None
    source: str = Field(min_length=1, max_length=80)
    intent: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = None
