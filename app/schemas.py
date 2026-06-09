from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from decimal import Decimal
from app.models import PledgeType, PledgeCategory, PledgeStatus, PaymentMode, UserRole


# ─── FAMILY ───────────────────────────────────────────────

class FamilyCreate(BaseModel):
    family_name: Optional[str] = None
    family_members_count: Optional[int] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    description: Optional[str] = None

class FamilyUpdate(BaseModel):
    family_name: Optional[str] = None
    family_members_count: Optional[int] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    description: Optional[str] = None

class FamilyOut(BaseModel):
    family_id: int
    family_name: Optional[str]
    family_members_count: Optional[int]
    address: Optional[str]
    phone: Optional[str]
    description: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ─── DONOR ────────────────────────────────────────────────

class DonorCreate(BaseModel):
    family_id: Optional[int] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    mobile: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    relation_in_family: Optional[str] = None
    is_anonymous: Optional[bool] = False
    description: Optional[str] = None

class DonorUpdate(BaseModel):
    family_id: Optional[int] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    mobile: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    relation_in_family: Optional[str] = None
    is_anonymous: Optional[bool] = None
    description: Optional[str] = None

class DonorOut(BaseModel):
    donor_id: int
    family_id: Optional[int]
    first_name: Optional[str]
    last_name: Optional[str]
    mobile: Optional[str]
    email: Optional[str]
    address: Optional[str]
    relation_in_family: Optional[str]
    is_anonymous: Optional[bool]
    description: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ─── EVENT ────────────────────────────────────────────────

class EventCreate(BaseModel):
    event_name: Optional[str] = None
    category: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    description: Optional[str] = None

class EventUpdate(BaseModel):
    event_name: Optional[str] = None
    category: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    description: Optional[str] = None

class EventOut(BaseModel):
    event_id: int
    event_name: Optional[str]
    category: Optional[str]
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    description: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ─── PLEDGE ───────────────────────────────────────────────

class PledgeCreate(BaseModel):
    donor_id: Optional[int] = None
    event_id: Optional[int] = None
    pledge_type: Optional[PledgeType] = None
    pledge_category: Optional[PledgeCategory] = None
    promised_amount: Optional[Decimal] = None
    item_name: Optional[str] = None
    item_category: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    market_value: Optional[Decimal] = None
    status: Optional[PledgeStatus] = PledgeStatus.PENDING
    description: Optional[str] = None

class PledgeUpdate(BaseModel):
    pledge_type: Optional[PledgeType] = None
    pledge_category: Optional[PledgeCategory] = None
    promised_amount: Optional[Decimal] = None
    item_name: Optional[str] = None
    item_category: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    market_value: Optional[Decimal] = None
    status: Optional[PledgeStatus] = None
    description: Optional[str] = None

class PledgeOut(BaseModel):
    pledge_id: int
    donor_id: Optional[int]
    event_id: Optional[int]
    pledge_type: Optional[PledgeType]
    pledge_category: Optional[PledgeCategory]
    promised_amount: Optional[Decimal]
    item_name: Optional[str]
    item_category: Optional[str]
    quantity: Optional[Decimal]
    unit: Optional[str]
    market_value: Optional[Decimal]
    status: Optional[PledgeStatus]
    description: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ─── PAYMENT ──────────────────────────────────────────────

class PaymentCreate(BaseModel):
    pledge_id: Optional[int] = None
    donor_name: Optional[str] = None
    amount: Optional[Decimal] = None
    payment_mode: Optional[PaymentMode] = None
    payment_ref: Optional[str] = None
    received_quantity: Optional[Decimal] = None
    receipt_no: Optional[str] = None
    description: Optional[str] = None
    recorded_by: Optional[str] = None
    payment_date: Optional[datetime] = None

class PaymentUpdate(BaseModel):
    donor_name: Optional[str] = None
    amount: Optional[Decimal] = None
    payment_mode: Optional[PaymentMode] = None
    payment_ref: Optional[str] = None
    received_quantity: Optional[Decimal] = None
    receipt_no: Optional[str] = None
    description: Optional[str] = None
    recorded_by: Optional[str] = None
    payment_date: Optional[datetime] = None

class PaymentOut(BaseModel):
    payment_id: int
    pledge_id: Optional[int]
    donor_name: Optional[str]
    amount: Optional[Decimal]
    payment_mode: Optional[PaymentMode]
    payment_ref: Optional[str]
    received_quantity: Optional[Decimal]
    receipt_no: Optional[str]
    description: Optional[str]
    recorded_by: Optional[str]
    payment_date: Optional[datetime]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ─── USER ─────────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str
    email: str
    phone_no: Optional[str] = None
    password: str  # plain text — hashed in the route/service layer
    role: Optional[UserRole] = UserRole.USER
    description: Optional[str] = None

class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    phone_no: Optional[str] = None
    description: Optional[str] = None

class UserOut(BaseModel):
    user_id: int
    username: Optional[str]
    email: Optional[str]
    phone_no: Optional[str]
    role: Optional[UserRole]
    description: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}  # password_hash intentionally excluded