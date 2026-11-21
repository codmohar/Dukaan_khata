"""Conversation Context Cache for DukaanAI Kirana Voice Assistant.

Maintains rolling conversational memory, customer context, product inquiries,
bill tallies, and multi-turn state transitions across shopkeeper-customer counter interactions.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import logging
import time
from typing import Any, Dict, List, Optional
import uuid

log = logging.getLogger("dukaan.agent.cache")


class ConversationState(str, Enum):
    IDLE = "IDLE"                                       # No active interaction
    INQUIRY = "INQUIRY"                                 # Item inquiry / selection ("Parle-G lena hai 15 rupaye ka")
    HANDOVER_BILLING = "HANDOVER_BILLING"               # Handover / bill announced ("Ye lo Parle-G, 15 rupaye hua")
    AWAITING_PAYMENT_CHOICE = "AWAITING_PAYMENT_CHOICE" # Trilemma prompt active: Cash, Promise, or Udhar
    DRAFT_PENDING = "DRAFT_PENDING"                     # Credit draft prepared, awaiting shopkeeper confirmation
    PROMISE_RECORDED = "PROMISE_RECORDED"               # Payment promise recorded
    SETTLED = "SETTLED"                                 # Transaction confirmed or walk-in paid


@dataclass
class CachedProduct:
    name: str
    qty: float = 1.0
    unit: str = "item"
    price: Optional[float] = None
    total: Optional[float] = None


@dataclass
class ConversationTurn:
    role: str       # "customer", "shopkeeper", "system", "user"
    text: str
    timestamp: float = field(default_factory=time.time)
    intent: Optional[str] = None
    entities: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationContextCache:
    shop_id: str
    state: ConversationState = ConversationState.IDLE
    active_customer_name: Optional[str] = None
    active_customer_id: Optional[str] = None
    active_customer_phone: Optional[str] = None
    active_member_name: Optional[str] = None
    active_member_id: Optional[str] = None
    active_products: List[Dict[str, Any]] = field(default_factory=list)
    pending_bill_amount: Optional[float] = None
    pending_bill_item: Optional[str] = None
    last_draft_id: Optional[str] = None
    active_disambiguation: Optional[List[Dict[str, Any]]] = None
    pending_undo_tid: Optional[str] = None
    turns: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_activity_ts: float = field(default_factory=time.time)

    def add_turn(
        self,
        role: str,
        text: str,
        intent: Optional[str] = None,
        entities: Optional[Dict[str, Any]] = None,
    ):
        """Append an utterance turn into the rolling sliding window (keeps last 8 turns)."""
        turn_entry = {
            "role": role,
            "text": text,
            "timestamp": time.time(),
            "intent": intent,
            "entities": entities or {},
        }
        self.turns.append(turn_entry)
        if len(self.turns) > 8:
            self.turns = self.turns[-8:]
        self.last_activity_ts = time.time()

    def set_inquiry(self, customer_name: Optional[str], product: Optional[str], amount: Optional[float]):
        """Record customer product inquiry / selection without creating premature ledger drafts."""
        if customer_name:
            self.active_customer_name = customer_name
        if product:
            self.pending_bill_item = product
            self.active_products.append({"name": product, "price": amount, "qty": 1})
        if amount is not None and amount > 0:
            self.pending_bill_amount = amount
        self.state = ConversationState.INQUIRY
        self.last_activity_ts = time.time()

    def set_bill_tally(self, amount: float, product: Optional[str] = None, customer_name: Optional[str] = None):
        """Record handover / bill announcement and transition to payment choice pending."""
        self.pending_bill_amount = amount
        if product:
            self.pending_bill_item = product
        if customer_name:
            self.active_customer_name = customer_name
        self.state = ConversationState.AWAITING_PAYMENT_CHOICE
        self.last_activity_ts = time.time()

    def reset_active_transaction(self, keep_customer: bool = False):
        """Reset active transactional slots when a sale is paid, confirmed, or cancelled."""
        self.pending_bill_amount = None
        self.pending_bill_item = None
        self.active_products.clear()
        self.last_draft_id = None
        self.active_disambiguation = None
        self.pending_undo_tid = None
        self.state = ConversationState.IDLE
        if not keep_customer:
            self.active_customer_name = None
            self.active_customer_id = None
            self.active_customer_phone = None
            self.active_member_name = None
            self.active_member_id = None
        self.last_activity_ts = time.time()

    def is_expired(self, ttl_seconds: float = 240.0) -> bool:
        """Kirana counter interactions generally settle in 2-3 minutes. Expire stale contexts."""
        return (time.time() - self.last_activity_ts) > ttl_seconds

    def to_dict(self) -> Dict[str, Any]:
        """Serialize cache state for inspection or structured logging."""
        return {
            "shop_id": self.shop_id,
            "state": self.state.value if isinstance(self.state, ConversationState) else str(self.state),
            "customer_name": self.active_customer_name,
            "customer_id": self.active_customer_id,
            "pending_bill_amount": self.pending_bill_amount,
            "pending_bill_item": self.pending_bill_item,
            "active_products": list(self.active_products),
            "last_draft_id": self.last_draft_id,
            "turn_count": len(self.turns),
            "idle_seconds": round(time.time() - self.last_activity_ts, 1),
        }


class ShopConversationCacheManager:
    """Manages active conversational context caches keyed by shop_id."""

    _caches: Dict[str, ConversationContextCache] = {}

    @classmethod
    def get_cache(cls, shop_id: str) -> ConversationContextCache:
        clean_sid = None
        if shop_id:
            s_val = str(shop_id).strip()
            if s_val and s_val.lower() not in ("undefined", "null", "none"):
                try:
                    clean_sid = str(uuid.UUID(s_val))
                except Exception:
                    clean_sid = s_val
        if not clean_sid:
            clean_sid = "00000000-0000-0000-0000-000000000001"

        cache = cls._caches.get(clean_sid)
        if cache is None:
            cache = ConversationContextCache(shop_id=clean_sid)
            cls._caches[clean_sid] = cache
        elif cache.is_expired():
            # Auto-reset stale active transaction context if inactivity exceeds TTL
            log.info("Conversation cache for shop %s expired (inactivity > 240s). Resetting.", clean_sid)
            cache.reset_active_transaction(keep_customer=False)
            cache.last_activity_ts = time.time()

        return cache

    @classmethod
    def clear_cache(cls, shop_id: str):
        if shop_id in cls._caches:
            del cls._caches[shop_id]

