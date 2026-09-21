from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import Optional

class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    industry: str = Field(min_length=2, max_length=80)

class TenantOut(TenantCreate):
    id: str
    model_config = ConfigDict(from_attributes=True)

class TenantProfileUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    industry: str = Field(min_length=2, max_length=80)
    description: Optional[str] = None
    phone: Optional[str] = Field(default=None, max_length=32)
    whatsapp_number: Optional[str] = Field(default=None, max_length=32)
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    website: Optional[str] = None
    timezone: str = "Asia/Kolkata"

class ServiceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: Optional[str] = None
    price: Optional[float] = Field(default=None, ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    duration_minutes: Optional[int] = Field(default=None, ge=1)
    is_active: bool = True

class ProductCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: Optional[str] = None
    price: Optional[float] = Field(default=None, ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    sku: Optional[str] = Field(default=None, max_length=80)
    stock_quantity: Optional[int] = Field(default=None, ge=0)
    is_active: bool = True

class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    business_name: str = Field(min_length=2, max_length=160)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    industry: str = Field(min_length=2, max_length=80)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

class UserOut(BaseModel):
    id: str
    email: str
    name: str
    tenant_id: str
    role: str

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
    tenant: TenantOut

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
