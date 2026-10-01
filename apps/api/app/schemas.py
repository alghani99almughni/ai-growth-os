from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import Optional
from datetime import datetime

class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    industry: str = Field(min_length=2, max_length=80)

class TenantOut(TenantCreate):
    # Platform admin uses an internal tenant slug (__platform__). Keep
    # normal tenant creation restricted to URL-safe slugs while allowing
    # this internal tenant to be returned by authentication endpoints.
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9_-]+$")
    id: str
    status: str = "active"
    description: Optional[str] = None
    phone: Optional[str] = None
    whatsapp_number: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    website: Optional[str] = None
    timezone: str = "Asia/Kolkata"
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
    name: str = Field(min_length=1, max_length=160)
    whatsapp_opt_in: bool = False
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    tags: str = ""
    source: str = "manual"

class LeadCreate(BaseModel):
    tenant_id: str
    customer_id: Optional[str] = None
    source: str = Field(min_length=1, max_length=80)
    intent: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = None


class BusinessHourInput(BaseModel):
    weekday: int = Field(ge=0, le=6)
    open_time: str = "09:00"
    close_time: str = "18:00"
    is_closed: bool = False
    slot_interval_minutes: int = Field(default=30, ge=5, le=120)

class QueueSettingsInput(BaseModel):
    queue_enabled: bool = True
    queue_threshold: int = Field(default=5, ge=0, le=1000)
    queue_avg_service_minutes: int = Field(default=15, ge=1, le=240)

class AppointmentCreate(BaseModel):
    customer_id: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None
    service_id: str
    starts_at: datetime
    staff_id: Optional[str] = None
    notes: Optional[str] = None
    source: str = "manual"
    queue_if_busy: bool = True
    force_queue: bool = False

class AppointmentStatusUpdate(BaseModel):
    status: str = Field(pattern=r"^(requested|confirmed|checked_in|serving|completed|cancelled|no_show)$")

class QueueCheckIn(BaseModel):
    force: bool = False


class ServiceRequestCreate(BaseModel):
    request_type: str = "waiter"
    message: Optional[str] = None
    context_token: Optional[str] = None
    customer_id: Optional[str] = None

class ServiceRequestStatusUpdate(BaseModel):
    status: str = Field(pattern=r"^(requested|acknowledged|in_progress|completed|cancelled)$")

class FeatureUpdate(BaseModel):
    features: dict[str,bool]

class GoogleReviewUpdate(BaseModel):
    review_url: str | None = None

class MenuCategoryCreate(BaseModel):
    name: str = Field(min_length=1,max_length=120)
    sort_order: int = 0
    is_active: bool = True

class MenuItemCreate(BaseModel):
    name: str = Field(min_length=1,max_length=160)
    category_id: str | None = None
    description: str | None = None
    price: int = Field(ge=0)
    currency: str = "INR"
    image_url: str | None = None
    is_active: bool = True
    is_available: bool = True
    sort_order: int = 0

class PublicOrderItem(BaseModel):
    menu_item_id: str
    quantity: int = Field(ge=1,le=50)
    notes: str | None = None

class PublicOrderCreate(BaseModel):
    items: list[PublicOrderItem] = Field(min_length=1,max_length=50)
    context_token: str | None = None
    customer_id: str | None = None

class OrderStatusUpdate(BaseModel):
    status: str = Field(pattern=r"^(pending|confirmed|preparing|ready|assigned|served|completed|cancelled)$")

class FeedbackCreate(BaseModel):
    order_id: str | None = None
    customer_id: str | None = None
    rating: int = Field(ge=1,le=5)
    food_rating: int | None = Field(default=None,ge=1,le=5)
    service_rating: int | None = Field(default=None,ge=1,le=5)
    comment: str | None = None

class LoyaltyRuleCreate(BaseModel):
    event_type: str = Field(min_length=2, max_length=60)
    name: str = Field(min_length=2, max_length=160)
    points: int = Field(ge=0, le=100000)
    is_active: bool = True
    config: dict = {}

class LoyaltyRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    points: int | None = Field(default=None, ge=0, le=100000)
    is_active: bool | None = None
    config: dict | None = None

class LoyaltyRewardCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    points_cost: int = Field(ge=1, le=10000000)
    description: str | None = None
    is_active: bool = True

class LoyaltyRewardUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    points_cost: int | None = Field(default=None, ge=1, le=10000000)
    description: str | None = None
    is_active: bool | None = None

class LoyaltyRedeemRequest(BaseModel):
    customer_id: str
    reward_id: str

class PaymentVerify(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class WhatsAppConnectionConfig(BaseModel):
    provider: str = Field(pattern=r"^(openwa|meta)$")
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    session_id: Optional[str] = None
    access_token: Optional[str] = None
    phone_number_id: Optional[str] = None
    waba_id: Optional[str] = None
    connected_phone: Optional[str] = Field(default=None, max_length=32)
    display_name: Optional[str] = Field(default=None, max_length=160)

class WhatsAppConnectionStatus(BaseModel):
    provider: str
    status: str
    connected_phone: Optional[str] = None
    display_name: Optional[str] = None
    configured: bool


class TenantProvisionRequest(BaseModel):
    business_name: str = Field(min_length=2, max_length=160)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    industry: str = Field(min_length=2, max_length=80)
    owner_name: str = Field(min_length=2, max_length=160)
    owner_email: EmailStr
    owner_password: str = Field(min_length=8, max_length=128)
    phone: Optional[str] = Field(default=None, max_length=32)
    whatsapp_number: Optional[str] = Field(default=None, max_length=32)
    address: Optional[str] = None
    template: Optional[str] = None

class DepartmentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: Optional[str] = None
    skills: str = ""

class RoleDefinitionCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    permissions: list[str] = []

class StaffCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: str = "staff"
    department_id: Optional[str] = None
    skills: str = ""

class StaffUpdate(BaseModel):
    role: Optional[str] = None
    department_id: Optional[str] = None
    skills: Optional[str] = None
    is_active: Optional[bool] = None
    is_available: Optional[bool] = None


class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=20, max_length=300)
    password: str = Field(min_length=8, max_length=128)
