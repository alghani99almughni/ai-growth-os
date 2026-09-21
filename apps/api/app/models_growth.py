from datetime import datetime,date,time
from sqlalchemy import String,DateTime,ForeignKey,Text,Boolean,Integer,Time,Date
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base
import uuid
def uid(): return str(uuid.uuid4())
class KnowledgeItem(Base):
    __tablename__="knowledge_items"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid); tenant_id:Mapped[str]=mapped_column(ForeignKey("tenants.id"),index=True); title:Mapped[str]=mapped_column(String(200)); content:Mapped[str]=mapped_column(Text); kind:Mapped[str]=mapped_column(String(40),default="faq"); is_active:Mapped[bool]=mapped_column(Boolean,default=True); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
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
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid); tenant_id:Mapped[str]=mapped_column(ForeignKey("tenants.id"),index=True); customer_id:Mapped[str|None]=mapped_column(ForeignKey("customers.id"),nullable=True); source:Mapped[str]=mapped_column(String(40),default="webrtc"); status:Mapped[str]=mapped_column(String(40),default="created"); department:Mapped[str|None]=mapped_column(String(80),nullable=True); staff_id:Mapped[str|None]=mapped_column(ForeignKey("staff_members.id"),nullable=True,index=True); transcript:Mapped[str|None]=mapped_column(Text,nullable=True); summary:Mapped[str|None]=mapped_column(Text,nullable=True); intent:Mapped[str|None]=mapped_column(String(120),nullable=True); room_id:Mapped[str|None]=mapped_column(String(80),nullable=True,index=True); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class Campaign(Base):
    __tablename__="campaigns"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid); tenant_id:Mapped[str]=mapped_column(ForeignKey("tenants.id"),index=True); name:Mapped[str]=mapped_column(String(160)); source:Mapped[str]=mapped_column(String(80)); scans:Mapped[int]=mapped_column(Integer,default=0); leads:Mapped[int]=mapped_column(Integer,default=0); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
