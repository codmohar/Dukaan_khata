import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, JSON, Numeric, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Shop(Base):
    __tablename__ = "shops"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(Text, default="Sri Lakshmi Kirana Store")
    owner_name: Mapped[str | None] = mapped_column(Text, nullable=True, default="Manjunath Gowda")
    phone: Mapped[str | None] = mapped_column(Text, nullable=True, default="+91 98450 00000")
    language: Mapped[str] = mapped_column(Text, default="kn-IN")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    customers = relationship("Customer", back_populates="shop", cascade="all, delete-orphan")


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    landmark: Mapped[str | None] = mapped_column(Text, nullable=True)
    outstanding_balance: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    shop = relationship("Shop", back_populates="customers")
    transactions = relationship("Transaction", back_populates="customer", cascade="all, delete-orphan")
    household_members = relationship("HouseholdMember", back_populates="customer", cascade="all, delete-orphan")
    promises = relationship("Promise", back_populates="customer")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)  # 'credit' | 'payment' | 'adjustment'
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payment_mode: Mapped[str | None] = mapped_column(Text, nullable=True)  # 'cash' | 'upi' | 'other'
    adjustment_reason: Mapped[str | None] = mapped_column(Text, nullable=True)  # 'discount' | 'return' | 'write_off' | 'correction'
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    backdated_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    items: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="draft")  # 'draft' | 'confirmed' | 'cancelled'
    source: Mapped[str] = mapped_column(Text, default="voice")  # 'voice' | 'scan' | 'manual'
    scan_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("household_members.id", ondelete="SET NULL"), nullable=True, index=True
    )
    item_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_warnings: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, default=list)
    transcript_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_override: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    customer = relationship("Customer", back_populates="transactions")
    member = relationship("HouseholdMember", back_populates="transactions")


class HouseholdMember(Base):
    __tablename__ = "household_members"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    member_name: Mapped[str] = mapped_column(Text, nullable=False)
    relationship_label: Mapped[str | None] = mapped_column("relationship", Text, nullable=True)
    is_authorized: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    customer = relationship("Customer", back_populates="household_members")
    transactions = relationship("Transaction", back_populates="member")


class Promise(Base):
    __tablename__ = "promises"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("household_members.id", ondelete="SET NULL"), nullable=True
    )
    entity_name: Mapped[str] = mapped_column(Text, nullable=False)
    promise_type: Mapped[str] = mapped_column(Text, nullable=False)  # 'PAYMENT_PROMISE' | 'GOODS_RESERVATION' | 'SUPPLIER_DELIVERY'
    promised_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    expected_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="PENDING")  # 'PENDING' | 'FULFILLED' | 'OVERDUE' | 'CANCELLED'
    fulfilled_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
    )
    source_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    fulfilled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    customer = relationship("Customer", back_populates="promises")


class ShopRule(Base):
    __tablename__ = "shop_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    rule_category: Mapped[str] = mapped_column(Text, nullable=False)  # 'NEW_CUSTOMER_CAP' | 'BALANCE_CAP' | 'TIME_CUTOFF' | 'MEMBER_AUTH' | 'CUSTOM_NOTE'
    rule_text: Mapped[str] = mapped_column(Text, nullable=False)
    structured_condition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DailyReconciliation(Base):
    __tablename__ = "daily_reconciliations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    reconciliation_date: Mapped[date] = mapped_column(Date, nullable=False)
    recorded_cash: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    actual_cash: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    recorded_upi: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    actual_upi: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    cash_difference: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    upi_difference: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)  # 'MATCHED' | 'NEEDS_INVESTIGATION' | 'RESOLVED'
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    audit_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="pending")  # 'pending' | 'sent' | 'dismissed'
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
