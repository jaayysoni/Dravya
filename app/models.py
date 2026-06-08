from sqlalchemy import Column, Integer, String, Text, Boolean, Numeric, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.database import Base


class PledgeType(enum.Enum):
    CASH = "CASH"
    LABH = "LABH"
    IN_KIND = "IN_KIND"


class PledgeCategory(enum.Enum):
    DONATION = "DONATION"
    ROLE = "ROLE"


class PledgeStatus(enum.Enum):
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    COMPLETED = "COMPLETED"


class PaymentMode(enum.Enum):
    CASH = "CASH"
    UPI = "UPI"
    CHEQUE = "CHEQUE"
    NEFT = "NEFT"


class UserRole(enum.Enum):
    ADMIN = "ADMIN"
    USER = "USER"


class Family(Base):
    __tablename__ = "families"

    family_id = Column(Integer, primary_key=True, index=True)
    family_name = Column(String, nullable=True)
    family_members_count = Column(Integer, nullable=True)
    address = Column(Text, nullable=True)
    phone = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    donors = relationship("Donor", back_populates="family")


class Donor(Base):
    __tablename__ = "donors"

    donor_id = Column(Integer, primary_key=True, index=True)
    family_id = Column(Integer, ForeignKey("families.family_id"), nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    mobile = Column(String, nullable=True)
    email = Column(String, nullable=True)
    address = Column(Text, nullable=True)
    relation_in_family = Column(String, nullable=True)
    is_anonymous = Column(Boolean, default=False, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    family = relationship("Family", back_populates="donors")
    pledges = relationship("Pledge", back_populates="donor")


class Event(Base):
    __tablename__ = "events"

    event_id = Column(Integer, primary_key=True, index=True)
    event_name = Column(String, nullable=True)
    category = Column(String, nullable=True)
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    pledges = relationship("Pledge", back_populates="event")


class Pledge(Base):
    __tablename__ = "pledges"

    pledge_id = Column(Integer, primary_key=True, index=True)
    donor_id = Column(Integer, ForeignKey("donors.donor_id"), nullable=True)
    event_id = Column(Integer, ForeignKey("events.event_id"), nullable=True)
    pledge_type = Column(Enum(PledgeType), nullable=True)
    pledge_category = Column(Enum(PledgeCategory), nullable=True)
    promised_amount = Column(Numeric(12, 2), nullable=True)
    item_name = Column(String, nullable=True)
    item_category = Column(String, nullable=True)
    quantity = Column(Numeric(10, 2), nullable=True)
    unit = Column(String, nullable=True)
    market_value = Column(Numeric(12, 2), nullable=True)
    status = Column(Enum(PledgeStatus), default=PledgeStatus.PENDING, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    donor = relationship("Donor", back_populates="pledges")
    event = relationship("Event", back_populates="pledges")
    payments = relationship("Payment", back_populates="pledge")


class Payment(Base):
    __tablename__ = "payments"

    payment_id = Column(Integer, primary_key=True, index=True)
    pledge_id = Column(Integer, ForeignKey("pledges.pledge_id"), nullable=True)
    donor_name = Column(String, nullable=True)
    amount = Column(Numeric(12, 2), nullable=True)
    payment_mode = Column(Enum(PaymentMode), nullable=True)
    payment_ref = Column(String, nullable=True)
    received_quantity = Column(Numeric(10, 2), nullable=True)
    receipt_no = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    recorded_by = Column(String, nullable=True)
    payment_date = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    pledge = relationship("Pledge", back_populates="payments")


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=True)
    email = Column(String, unique=True, nullable=True)
    phone_no = Column(String, nullable=True)
    password_hash = Column(String, nullable=True)
    role = Column(Enum(UserRole), default=UserRole.USER, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())