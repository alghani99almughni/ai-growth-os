from datetime import datetime,date,time
from sqlalchemy import String,DateTime,ForeignKey,Text,Boolean,Integer,Time,Date
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base
import uuid
def uid(): return str(uuid.uuid4())
class AIProviderUsage(Base):
    __tablename__="ai_provider_usage"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    tenant_id:Mapped[str|None]=mapped_column(ForeignKey("tenants.id"),nullable=True,index=True)
    provider:Mapped[str]=mapped_column(String(60),index=True)
    model:Mapped[str]=mapped_column(String(120))
    credential_ref:Mapped[str]=mapped_column(String(32),index=True,default="default")
    request_count:Mapped[int]=mapped_column(Integer,default=0)
    success_count:Mapped[int]=mapped_column(Integer,default=0)
    failure_count:Mapped[int]=mapped_column(Integer,default=0)
    rate_limit_count:Mapped[int]=mapped_column(Integer,default=0)
    estimated_input_tokens:Mapped[int]=mapped_column(Integer,default=0)
    estimated_output_tokens:Mapped[int]=mapped_column(Integer,default=0)
    last_error:Mapped[str|None]=mapped_column(Text,nullable=True)
    last_used_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    cooldown_until:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

class KnowledgeItem(Base):
    __tablename__="knowledge_items"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    tenant_id:Mapped[str]=mapped_column(ForeignKey("tenants.id"),index=True)
    title:Mapped[str]=mapped_column(String(200))
    content:Mapped[str]=mapped_column(Text)
    kind:Mapped[str]=mapped_column(String(40),default="faq")
    language:Mapped[str]=mapped_column(String(16),default="en",index=True)
    source:Mapped[str]=mapped_column(String(60),default="manual")
    approval_status:Mapped[str]=mapped_column(String(30),default="approved",index=True)
    usage_count:Mapped[int]=mapped_column(Integer,default=0)
    last_used_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    embedding_json:Mapped[str|None]=mapped_column(Text,nullable=True)
    embedding_model:Mapped[str|None]=mapped_column(String(80),nullable=True)
    is_active:Mapped[bool]=mapped_column(Boolean,default=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

class KnowledgeCandidate(Base):
    __tablename__="knowledge_candidates"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    tenant_id:Mapped[str]=mapped_column(ForeignKey("tenants.id"),index=True)
    question:Mapped[str]=mapped_column(Text)
    answer:Mapped[str]=mapped_column(Text)
    language:Mapped[str]=mapped_column(String(16),default="en",index=True)
    intent:Mapped[str|None]=mapped_column(String(120),nullable=True,index=True)
    status:Mapped[str]=mapped_column(String(30),default="pending",index=True)
    source:Mapped[str]=mapped_column(String(40),default="voice")
    provider:Mapped[str]=mapped_column(String(60),default="ai")
    times_asked:Mapped[int]=mapped_column(Integer,default=1)
    first_asked_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    last_asked_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,index=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class BusinessHour(Base):
    __tablename__="business_hours"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    tenant_id:Mapped[str]=mapped_column(ForeignKey("tenants.id"),index=True)
    weekday:Mapped[int]=mapped_column(Integer)
    open_time:Mapped[time]=mapped_column(Time)
    close_time:Mapped[time]=mapped_column(Time)
    is_closed:Mapped[bool]=mapped_column(Boolean,default=False)
    slot_interval_minutes:Mapped[int]=mapped_column(Integer,default=30)

class Appointment(Base):
    __tablename__="appointments"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    tenant_id:Mapped[str]=mapped_column(ForeignKey("tenants.id"),index=True)
    customer_id:Mapped[str]=mapped_column(ForeignKey("customers.id"),index=True)
    service_id:Mapped[str|None]=mapped_column(ForeignKey("services.id"),nullable=True)
    staff_id:Mapped[str|None]=mapped_column(ForeignKey("staff_members.id"),nullable=True,index=True)
    starts_at:Mapped[datetime]=mapped_column(DateTime,index=True)
    ends_at:Mapped[datetime]=mapped_column(DateTime)
    status:Mapped[str]=mapped_column(String(40),default="requested",index=True)
    source:Mapped[str]=mapped_column(String(40),default="manual")
    queue_token:Mapped[str|None]=mapped_column(String(40),nullable=True,index=True)
    queue_status:Mapped[str|None]=mapped_column(String(40),nullable=True)
    notes:Mapped[str|None]=mapped_column(Text,nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

class QueueEntry(Base):
    __tablename__="queue_entries"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    tenant_id:Mapped[str]=mapped_column(ForeignKey("tenants.id"),index=True)
    appointment_id:Mapped[str]=mapped_column(ForeignKey("appointments.id"),unique=True,index=True)
    customer_id:Mapped[str]=mapped_column(ForeignKey("customers.id"),index=True)
    queue_date:Mapped[date]=mapped_column(Date)
    sequence:Mapped[int]=mapped_column(Integer)
    token:Mapped[str]=mapped_column(String(40),index=True)
    status:Mapped[str]=mapped_column(String(40),default="waiting",index=True)
    people_ahead:Mapped[int]=mapped_column(Integer,default=0)
    estimated_wait_minutes:Mapped[int]=mapped_column(Integer,default=0)
    called_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    completed_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class LoyaltyTransaction(Base):
    __tablename__="loyalty_transactions"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid); tenant_id:Mapped[str]=mapped_column(ForeignKey("tenants.id"),index=True); customer_id:Mapped[str]=mapped_column(ForeignKey("customers.id"),index=True); points:Mapped[int]=mapped_column(Integer); reason:Mapped[str]=mapped_column(String(160)); reference_id:Mapped[str|None]=mapped_column(String(100),nullable=True); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class QrEntry(Base):
    __tablename__="qr_entries"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid); tenant_id:Mapped[str]=mapped_column(ForeignKey("tenants.id"),index=True); token:Mapped[str]=mapped_column(String(100),unique=True,index=True); kind:Mapped[str]=mapped_column(String(40),default="business"); label:Mapped[str]=mapped_column(String(160)); scans:Mapped[int]=mapped_column(Integer,default=0); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class CallRecord(Base):
    __tablename__="call_records"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    tenant_id:Mapped[str]=mapped_column(ForeignKey("tenants.id"),index=True)
    customer_id:Mapped[str|None]=mapped_column(ForeignKey("customers.id"),nullable=True,index=True)
    source:Mapped[str]=mapped_column(String(40),default="webrtc")
    status:Mapped[str]=mapped_column(String(40),default="created",index=True)
    department:Mapped[str|None]=mapped_column(String(80),nullable=True)
    staff_id:Mapped[str|None]=mapped_column(ForeignKey("staff_members.id"),nullable=True,index=True)
    transcript:Mapped[str|None]=mapped_column(Text,nullable=True)
    summary:Mapped[str|None]=mapped_column(Text,nullable=True)
    intent:Mapped[str|None]=mapped_column(String(120),nullable=True,index=True)
    language:Mapped[str]=mapped_column(String(16),default="en",index=True)
    room_id:Mapped[str|None]=mapped_column(String(80),nullable=True,index=True)
    started_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    answered_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    ended_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    duration_seconds:Mapped[int]=mapped_column(Integer,default=0)
    call_number:Mapped[int]=mapped_column(Integer,default=1)
    resolution:Mapped[str|None]=mapped_column(String(50),nullable=True)
    knowledge_hits:Mapped[int]=mapped_column(Integer,default=0)
    ai_turns:Mapped[int]=mapped_column(Integer,default=0)
    human_callback_requested:Mapped[bool]=mapped_column(Boolean,default=False)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class Campaign(Base):
    __tablename__="campaigns"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid); tenant_id:Mapped[str]=mapped_column(ForeignKey("tenants.id"),index=True); name:Mapped[str]=mapped_column(String(160)); source:Mapped[str]=mapped_column(String(80)); scans:Mapped[int]=mapped_column(Integer,default=0); leads:Mapped[int]=mapped_column(Integer,default=0); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)


class ServiceRequest(Base):
    __tablename__="service_requests"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    tenant_id:Mapped[str]=mapped_column(ForeignKey("tenants.id"),index=True)
    customer_id:Mapped[str|None]=mapped_column(ForeignKey("customers.id"),nullable=True,index=True)
    appointment_id:Mapped[str|None]=mapped_column(ForeignKey("appointments.id"),nullable=True,index=True)
    context_token:Mapped[str|None]=mapped_column(String(100),nullable=True,index=True)
    request_type:Mapped[str]=mapped_column(String(50),default="waiter")
    message:Mapped[str|None]=mapped_column(Text,nullable=True)
    status:Mapped[str]=mapped_column(String(40),default="requested",index=True)
    assigned_staff_id:Mapped[str|None]=mapped_column(ForeignKey("staff_members.id"),nullable=True,index=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    acknowledged_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    completed_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)

class TenantSetting(Base):
    __tablename__="tenant_settings"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    tenant_id:Mapped[str]=mapped_column(ForeignKey("tenants.id"),index=True)
    key:Mapped[str]=mapped_column(String(120),index=True)
    value_json:Mapped[str]=mapped_column(Text,default="{}")
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

class MenuCategory(Base):
    __tablename__="menu_categories"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    tenant_id:Mapped[str]=mapped_column(ForeignKey("tenants.id"),index=True)
    name:Mapped[str]=mapped_column(String(120))
    sort_order:Mapped[int]=mapped_column(Integer,default=0)
    is_active:Mapped[bool]=mapped_column(Boolean,default=True)

class MenuItem(Base):
    __tablename__="menu_items"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    tenant_id:Mapped[str]=mapped_column(ForeignKey("tenants.id"),index=True)
    category_id:Mapped[str|None]=mapped_column(ForeignKey("menu_categories.id"),nullable=True,index=True)
    name:Mapped[str]=mapped_column(String(160))
    description:Mapped[str|None]=mapped_column(Text,nullable=True)
    price:Mapped[int]=mapped_column(Integer,default=0)
    currency:Mapped[str]=mapped_column(String(3),default="INR")
    image_url:Mapped[str|None]=mapped_column(String(500),nullable=True)
    is_active:Mapped[bool]=mapped_column(Boolean,default=True)
    is_available:Mapped[bool]=mapped_column(Boolean,default=True)
    sort_order:Mapped[int]=mapped_column(Integer,default=0)

class Order(Base):
    __tablename__="orders"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    tenant_id:Mapped[str]=mapped_column(ForeignKey("tenants.id"),index=True)
    customer_id:Mapped[str|None]=mapped_column(ForeignKey("customers.id"),nullable=True,index=True)
    context_token:Mapped[str|None]=mapped_column(String(100),nullable=True,index=True)
    status:Mapped[str]=mapped_column(String(40),default="pending",index=True)
    subtotal:Mapped[int]=mapped_column(Integer,default=0)
    tax:Mapped[int]=mapped_column(Integer,default=0)
    discount:Mapped[int]=mapped_column(Integer,default=0)
    total:Mapped[int]=mapped_column(Integer,default=0)
    payment_status:Mapped[str]=mapped_column(String(40),default="unpaid")
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    updated_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

class OrderItem(Base):
    __tablename__="order_items"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    order_id:Mapped[str]=mapped_column(ForeignKey("orders.id"),index=True)
    menu_item_id:Mapped[str|None]=mapped_column(ForeignKey("menu_items.id"),nullable=True)
    name:Mapped[str]=mapped_column(String(160))
    price:Mapped[int]=mapped_column(Integer,default=0)
    quantity:Mapped[int]=mapped_column(Integer,default=1)
    notes:Mapped[str|None]=mapped_column(Text,nullable=True)

class Bill(Base):
    __tablename__="bills"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    tenant_id:Mapped[str]=mapped_column(ForeignKey("tenants.id"),index=True)
    order_id:Mapped[str]=mapped_column(ForeignKey("orders.id"),unique=True,index=True)
    subtotal:Mapped[int]=mapped_column(Integer,default=0)
    tax:Mapped[int]=mapped_column(Integer,default=0)
    discount:Mapped[int]=mapped_column(Integer,default=0)
    total:Mapped[int]=mapped_column(Integer,default=0)
    status:Mapped[str]=mapped_column(String(40),default="issued")
    payment_id:Mapped[str|None]=mapped_column(String(120),nullable=True)
    issued_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    paid_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)

class Feedback(Base):
    __tablename__="feedback"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    tenant_id:Mapped[str]=mapped_column(ForeignKey("tenants.id"),index=True)
    customer_id:Mapped[str|None]=mapped_column(ForeignKey("customers.id"),nullable=True)
    order_id:Mapped[str|None]=mapped_column(ForeignKey("orders.id"),nullable=True,index=True)
    rating:Mapped[int]=mapped_column(Integer)
    food_rating:Mapped[int|None]=mapped_column(Integer,nullable=True)
    service_rating:Mapped[int|None]=mapped_column(Integer,nullable=True)
    comment:Mapped[str|None]=mapped_column(Text,nullable=True)
    ai_summary:Mapped[str|None]=mapped_column(Text,nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

class LoyaltyRule(Base):
    __tablename__="loyalty_rules"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    tenant_id:Mapped[str]=mapped_column(ForeignKey("tenants.id"),index=True)
    event_type:Mapped[str]=mapped_column(String(60),index=True)
    name:Mapped[str]=mapped_column(String(160))
    points:Mapped[int]=mapped_column(Integer)
    is_active:Mapped[bool]=mapped_column(Boolean,default=True)
    config_json:Mapped[str]=mapped_column(Text,default="{}")

class LoyaltyReward(Base):
    __tablename__="loyalty_rewards"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    tenant_id:Mapped[str]=mapped_column(ForeignKey("tenants.id"),index=True)
    name:Mapped[str]=mapped_column(String(160))
    points_cost:Mapped[int]=mapped_column(Integer)
    description:Mapped[str|None]=mapped_column(Text,nullable=True)
    is_active:Mapped[bool]=mapped_column(Boolean,default=True)

class GameScore(Base):
    __tablename__="game_scores"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    tenant_id:Mapped[str]=mapped_column(ForeignKey("tenants.id"),index=True)
    customer_id:Mapped[str|None]=mapped_column(ForeignKey("customers.id"),nullable=True)
    game:Mapped[str]=mapped_column(String(60))
    score:Mapped[int]=mapped_column(Integer,default=0)
    reward_points:Mapped[int]=mapped_column(Integer,default=0)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

class PlatformSetting(Base):
    __tablename__="platform_settings"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    key:Mapped[str]=mapped_column(String(160),unique=True,index=True)
    value_json:Mapped[str]=mapped_column(Text,default="{}")
    updated_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)


class PasswordResetToken(Base):
    __tablename__="password_reset_tokens"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    user_id:Mapped[str]=mapped_column(ForeignKey("users.id"),index=True)
    token_hash:Mapped[str]=mapped_column(String(128),unique=True,index=True)
    expires_at:Mapped[datetime]=mapped_column(DateTime,index=True)
    used_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
