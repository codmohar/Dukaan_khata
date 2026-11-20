from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CustomerIn(BaseModel):
    name: str = Field(..., min_length=1, description="Customer full or familiar name")
    phone: str | None = None
    landmark: str | None = None


class CustomerUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    landmark: str | None = None


class CustomerOut(CustomerIn):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    balance: Decimal = Decimal("0.00")
    created_at: datetime | None = None


class TransactionIn(BaseModel):
    customer_id: UUID
    member_id: UUID | None = None
    type: str = Field(..., pattern="^(credit|payment|adjustment)$", description="'credit' for udhar, 'payment' for jama, 'adjustment' for discount/return/write-off")
    amount: Decimal = Field(..., gt=0, le=10000000, description="Amount in rupees")
    payment_mode: str | None = Field(None, pattern="^(?i)(cash|upi|credit|other)$")
    adjustment_reason: str | None = Field(None, pattern="^(discount|return|write_off|correction)$")
    due_date: date | None = None
    backdated_to: date | None = None
    items: list[dict[str, Any]] | None = None
    item_note: str | None = None
    note: str | None = None
    status: str = Field("confirmed", pattern="^(draft|confirmed|cancelled)$")


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    customer_id: UUID
    member_id: UUID | None = None
    member_name: str | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    type: str
    amount: Decimal
    payment_mode: str | None = None
    adjustment_reason: str | None = None
    due_date: date | None = None
    backdated_to: date | None = None
    items: list[dict[str, Any]] | None = None
    item_note: str | None = None
    note: str | None = None
    rule_warnings: list[dict[str, Any]] | None = None
    rule_override: bool | None = None
    transcript_snippet: str | None = None
    status: str
    created_at: datetime
    confirmed_at: datetime | None = None


class DailySeries(BaseModel):
    date: str
    credit: float
    payment: float


class DashboardStats(BaseModel):
    total_outstanding: Decimal
    credit_today: Decimal
    payments_today: Decimal
    customer_count: int
    pending_drafts: int
    last_7_days: list[DailySeries]


class ShopOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    owner_name: str | None = None
    phone: str | None = None
    language: str


class ShopUpdate(BaseModel):
    name: str | None = None
    owner_name: str | None = None
    phone: str | None = None
    language: str | None = None


class DraftActionResponse(BaseModel):
    status: str
    draft_id: str | None = None
    new_balance: float | None = None


class VoiceTurnResponse(BaseModel):
    transcript: str
    reply: str
    audio_base64: str | None = None
    events: list[dict] = Field(default_factory=list)


# -------------------- ADVANCED FEATURES SCHEMAS --------------------

class HouseholdMemberIn(BaseModel):
    member_name: str = Field(..., min_length=1)
    relationship: str | None = None
    is_authorized: bool = True


class HouseholdMemberUpdate(BaseModel):
    member_name: str | None = None
    relationship: str | None = None
    is_authorized: bool | None = None


class HouseholdMemberOut(BaseModel):
    id: UUID
    member_name: str
    relationship: str | None = None
    is_authorized: bool
    created_at: str | None = None
    total_credit: float = 0.0
    total_payment: float = 0.0
    tx_count: int = 0


class ShopRuleIn(BaseModel):
    rule_category: str = Field(..., pattern="^(NEW_CUSTOMER_CAP|BALANCE_CAP|TIME_CUTOFF|MEMBER_AUTH|CUSTOM_NOTE)$")
    rule_text: str = Field(..., min_length=2)
    structured_condition: dict[str, Any]


class ShopRuleUpdate(BaseModel):
    is_active: bool | None = None
    rule_text: str | None = None
    structured_condition: dict[str, Any] | None = None


class ShopRuleOut(BaseModel):
    id: UUID
    rule_category: str
    rule_text: str
    structured_condition: dict[str, Any]
    is_active: bool
    created_at: str | None = None


class PromiseIn(BaseModel):
    entity_name: str = Field(..., min_length=1)
    promise_type: str = Field(..., pattern="^(PAYMENT_PROMISE|GOODS_RESERVATION|SUPPLIER_DELIVERY)$")
    description: str = Field(..., min_length=1)
    expected_date: date
    promised_amount: Decimal | None = None
    customer_id: UUID | None = None
    member_id: UUID | None = None


class PromiseUpdate(BaseModel):
    action: str = Field(..., pattern="^(?i)(FULFIL_MANUAL|CANCEL|RESCHEDULE)$")
    new_date: date | None = None


class PromiseOut(BaseModel):
    id: UUID
    customer_id: UUID | None = None
    customer_name: str | None = None
    member_id: UUID | None = None
    entity_name: str
    promise_type: str
    promised_amount: float | None = None
    description: str
    expected_date: str
    status: str
    fulfilled_transaction_id: UUID | None = None
    created_at: str | None = None
    fulfilled_at: str | None = None


class PromisesSummaryOut(BaseModel):
    due_today: int
    overdue: int
    total_pending_amount: float
    items: list[dict[str, Any]] = Field(default_factory=list)


class MemorySearchIn(BaseModel):
    entity_name: str | None = None
    keyword: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    scope: list[str] | None = None
    limit: int = 10


class ReconciliationIn(BaseModel):
    actual_cash: Decimal = Field(..., ge=0)
    actual_upi: Decimal = Field(..., ge=0)
    on_date: date | None = None
    notes: str | None = None


class ReconciliationResolveIn(BaseModel):
    note: str | None = None

