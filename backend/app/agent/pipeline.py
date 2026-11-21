"""Voice Turn Pipeline: PCM Audio -> STT -> Gemini 2.5 Flash (via LLMProvider) -> DB Tools -> TTS.

Implements the multi-stage voice ledger agent with strict function calling,
disambiguation handling, and confirmation guardrails.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from zoneinfo import ZoneInfo

from ..config import settings
from ..db import SessionLocal
from ..services import speech
from . import tools
from .conversation_cache import (
    ConversationContextCache,
    ConversationState,
    ShopConversationCacheManager,
)
from .fast_engine import try_fast_path
from .llm_provider import BaseLLMProvider, get_llm_provider
from .prompts import SYSTEM_PROMPT

log = logging.getLogger("dukaan.agent.pipeline")
MAX_TOOL_ROUNDS = 8


class VoiceSession:
    """Session state per WebSocket connection or conversational interaction."""

    def __init__(self, shop_id: str, language: str = "kn-IN", llm_provider: BaseLLMProvider | None = None):
        clean_sid = None
        if shop_id:
            s_val = str(shop_id).strip()
            if s_val and s_val.lower() not in ("undefined", "null", "none"):
                try:
                    clean_sid = str(uuid.UUID(s_val))
                except Exception:
                    pass
        if not clean_sid:
            try:
                clean_sid = str(uuid.UUID(str(settings.default_shop_id).strip()))
            except Exception:
                clean_sid = "00000000-0000-0000-0000-000000000001"
        self.shop_id = clean_sid
        self.language = language
        self.llm = llm_provider or get_llm_provider()
        self.history: List[Dict[str, Any]] = []
        self.turn = 0
        self.last_draft_id: str | None = None
        self.pending_draft_ids: List[str] | None = None
        self.draft_turn: Dict[str, int] = {}  # draft_id -> turn in which it was drafted
        self.undo_inspected_turn: int = 0     # turn in which last confirmed undo was inspected

        # Multi-turn conversational context slots
        self.active_customer_id: str | None = None
        self.active_customer_name: str | None = None
        self.active_amount: float | None = None
        self.active_tx_type: str | None = None
        self.active_payment_mode: str | None = None
        self.active_disambiguation: List[Dict[str, Any]] | None = None
        self.pending_undo_tid: str | None = None
        self.pending_bill_amount: float | None = None
        self.pending_bill_item: str | None = None
        self.greeting_given: bool = False

        # Rolling conversation context cache for multi-turn counter interactions
        self.cache = ShopConversationCacheManager.get_cache(self.shop_id)
        if self.cache.active_customer_name:
            self.active_customer_name = self.cache.active_customer_name
        if self.cache.pending_bill_amount:
            self.pending_bill_amount = self.cache.pending_bill_amount
        if self.cache.pending_bill_item:
            self.pending_bill_item = self.cache.pending_bill_item
        if self.cache.last_draft_id:
            self.last_draft_id = self.cache.last_draft_id

    async def transcribe(self, pcm: bytes) -> str:
        """Convert raw 16kHz PCM audio to text."""
        return await speech.transcribe(pcm, self.language)

    async def synthesize(self, text: str) -> bytes:
        """Convert response text to WAV audio."""
        return await speech.synthesize(text, self.language)

    async def respond(self, user_text: str) -> Tuple[str, List[Dict[str, Any]]]:
        """Execute one conversational turn.

        Returns (reply_text, ui_events).
        """
        self.turn += 1
        events: List[Dict[str, Any]] = []
        self.cache.add_turn(role="user", text=user_text)

        # Keep recent sliding window cleanly aligned on a user text turn boundary
        if len(self.history) > 36:
            cut = len(self.history) - 24
            while cut < len(self.history):
                m = self.history[cut]
                if m.get("role") == "user" and any("text" in p for p in m.get("parts", []) if isinstance(p, dict)):
                    break
                cut += 1
            self.history = self.history[cut:]

        # Append user turn to history
        self.history.append({
            "role": "user",
            "parts": [{"text": user_text}],
        })

        # High-Speed Fast-Path & Ambient Chatter Sieve (sub-20ms execution)
        fast_res = await try_fast_path(
            session_or_shop_id=self,
            user_text=user_text,
            language=self.language,
            last_draft_id=self.last_draft_id,
        )
        if fast_res.handled:
            if fast_res.events:
                for ev in fast_res.events:
                    if ev.get("type") == "draft":
                        self.last_draft_id = ev.get("draft_id")
                        self.draft_turn[ev["draft_id"]] = self.turn
                        self.cache.last_draft_id = ev.get("draft_id")
                    elif ev.get("type") in ("confirmed", "cancelled"):
                        self.last_draft_id = None
                        self.cache.last_draft_id = None
            if fast_res.reply != "[SILENT]":
                self.history.append({"role": "model", "parts": [{"text": fast_res.reply}]})
                self.cache.add_turn(role="assistant", text=fast_res.reply)
            return fast_res.reply, fast_res.events

        IST = ZoneInfo("Asia/Kolkata")
        now_ist = datetime.now(IST)
        dynamic_prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"Current Context: Today is {now_ist.strftime('%A, %Y-%m-%d %I:%M %p')} IST (Asia/Kolkata).\n"
            f"Active session language preference: {self.language}."
        )

        async with SessionLocal() as s:
            for round_idx in range(MAX_TOOL_ROUNDS):
                llm_res = await self.llm.chat_turn(
                    history=self.history,
                    tools_declarations=tools.DECLARATIONS,
                    system_instruction=dynamic_prompt,
                )

                # Append assistant model response to history
                if hasattr(llm_res, "raw_parts") and llm_res.raw_parts:
                    model_parts = llm_res.raw_parts
                else:
                    model_parts: List[Dict[str, Any]] = []
                    if llm_res.text:
                        model_parts.append({"text": llm_res.text})
                    for fc in llm_res.function_calls:
                        model_parts.append({"function_call": fc})

                self.history.append({
                    "role": "model",
                    "parts": model_parts,
                })

                # If no function calls, agent has generated final reply
                if not llm_res.function_calls:
                    final_text = (llm_res.text or "").strip()
                    if not events and (not final_text or final_text.upper().startswith("[SILENT]")):
                        return "[SILENT]", events
                    if not final_text:
                        if self.language.startswith("kn"):
                            final_text = "Samajh aaglilla, dayavittu innomme heli."
                        elif self.language.startswith("hi"):
                            final_text = "Samajh nahi aaya, kripya dobara bolein."
                        else:
                            final_text = "Could not understand, please speak again."
                    return final_text, events

                # Execute all function calls requested in this turn
                tool_results_parts: List[Dict[str, Any]] = []
                for fc in llm_res.function_calls:
                    fname = fc["name"]
                    fargs = dict(fc.get("args") or {})
                    out = await self._run_tool(s, fname, fargs, user_text, events)
                    tool_results_parts.append({
                        "function_response": {
                            "name": fname,
                            "response": {"result": out},
                        }
                    })

                # Send tool execution results back to LLM
                self.history.append({
                    "role": "user",
                    "parts": tool_results_parts,
                })

        return "Could not complete the request. Please try again.", events

    async def _run_tool(
        self,
        s,
        name: str,
        args: Dict[str, Any],
        transcript: str,
        events: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Dispatch tool calls to database functions with validation and guardrails."""
        sid = self.shop_id
        try:
            if name == "search_customers":
                return await tools.search_customers(s, sid, str(args.get("name", "")))

            if name == "create_customer":
                return await tools.create_customer(
                    s,
                    sid,
                    name=str(args["name"]),
                    phone=args.get("phone"),
                    landmark=args.get("landmark"),
                )

            if name == "get_balance":
                return await tools.get_balance(s, sid, str(args["customer_id"]))

            if name == "get_shop_summary":
                return await tools.get_shop_summary(s, sid)

            if name == "update_customer":
                return await tools.update_customer(
                    s,
                    sid,
                    customer_id=str(args["customer_id"]),
                    phone=args.get("phone"),
                    landmark=args.get("landmark"),
                    name=args.get("name"),
                )

            if name == "create_draft":
                out = await tools.create_draft(
                    s,
                    sid,
                    customer_id=str(args["customer_id"]),
                    type=str(args["type"]),
                    amount=float(args["amount"]),
                    payment_mode=args.get("payment_mode"),
                    adjustment_reason=args.get("adjustment_reason"),
                    due_date=args.get("due_date"),
                    backdated_to=args.get("backdated_to"),
                    items=args.get("items"),
                    note=args.get("note"),
                    transcript=transcript,
                    language=self.language,
                    member_id=args.get("member_id"),
                    item_note=args.get("item_note"),
                )
                if "draft_id" in out:
                    self.last_draft_id = out["draft_id"]
                    self.draft_turn[out["draft_id"]] = self.turn
                    events.append({**out, "tx_type": out["type"], "type": "draft"})
                    if out.get("rule_warnings"):
                        events.append({"type": "rule_warning", **out})
                return out

            if name == "resolve_household_member":
                return await tools.resolve_household_member(
                    s,
                    sid,
                    customer_name=str(args["customer_name"]),
                    member_name=args.get("member_name"),
                    relationship=args.get("relationship"),
                )

            if name == "add_household_member":
                return await tools.add_household_member(
                    s,
                    sid,
                    customer_id=str(args["customer_id"]),
                    member_name=str(args["member_name"]),
                    relationship=args.get("relationship"),
                    is_authorized=bool(args.get("is_authorized", True)),
                )

            if name == "save_shop_rule":
                out = await tools.save_shop_rule(
                    s,
                    sid,
                    rule_category=str(args["rule_category"]),
                    rule_text=str(args["rule_text"]),
                    structured_condition=dict(args.get("structured_condition") or {}),
                )
                if "rule_id" in out:
                    events.append({"type": "rule_card", **out})
                return out

            if name == "override_rule_warnings":
                return await tools.override_rule_warnings(s, sid, str(args["draft_id"]))

            if name == "create_promise":
                out = await tools.create_promise(
                    s,
                    sid,
                    entity_name=str(args["entity_name"]),
                    promise_type=str(args["promise_type"]),
                    description=str(args["description"]),
                    expected_date=str(args["expected_date"]),
                    promised_amount=float(args["promised_amount"]) if args.get("promised_amount") else None,
                    customer_id=args.get("customer_id"),
                    member_id=args.get("member_id"),
                    transcript=transcript,
                )
                if "promise_id" in out:
                    events.append({"type": "promise_card", **out})
                return out

            if name == "list_promises":
                return await tools.list_promises(
                    s,
                    sid,
                    status=args.get("status"),
                    on_date=args.get("on_date"),
                    customer_name=args.get("customer_name"),
                    customer_id=args.get("customer_id"),
                )

            if name == "update_promise":
                return await tools.update_promise(
                    s,
                    sid,
                    promise_id=str(args["promise_id"]),
                    action=str(args["action"]),
                    new_date=args.get("new_date"),
                )

            if name == "fulfil_entity_promise":
                return await tools.fulfil_entity_promise(
                    s,
                    sid,
                    entity_name=str(args["entity_name"]),
                )

            if name == "search_shop_memory":
                return await tools.search_shop_memory(
                    s,
                    sid,
                    entity_name=args.get("entity_name"),
                    keyword=args.get("keyword"),
                    date_from=args.get("date_from"),
                    date_to=args.get("date_to"),
                    scope=args.get("scope"),
                )

            if name == "get_dispute_timeline":
                out = await tools.get_dispute_timeline(
                    s,
                    sid,
                    customer_id=str(args["customer_id"]),
                    limit=int(args.get("limit", 5)),
                    member_id=args.get("member_id"),
                )
                if "rows" in out:
                    events.append({"type": "timeline", **out})
                return out

            if name == "start_reconciliation":
                out = await tools.start_reconciliation(s, sid, on_date=args.get("on_date"))
                if "recorded_cash" in out:
                    events.append({"type": "reconciliation_prompt", **out})
                return out

            if name == "run_daily_reconciliation":
                out = await tools.run_daily_reconciliation(
                    s,
                    sid,
                    actual_cash=float(args["actual_cash"]),
                    actual_upi=float(args["actual_upi"]),
                    on_date=args.get("on_date"),
                    notes=args.get("notes"),
                )
                if "reconciliation_id" in out:
                    events.append({"type": "reconciliation_result", **out})
                return out

            if name == "settle_balance":
                out = await tools.settle_balance(
                    s,
                    sid,
                    customer_id=str(args["customer_id"]),
                    payment_mode=args.get("payment_mode"),
                    is_write_off=bool(args.get("is_write_off", False)),
                    note=args.get("note"),
                    transcript=transcript,
                    language=self.language,
                )
                if "draft_id" in out:
                    self.last_draft_id = out["draft_id"]
                    self.draft_turn[out["draft_id"]] = self.turn
                    events.append({**out, "tx_type": out["type"], "type": "draft"})
                return out

            if name == "prepare_reminder":
                out = await tools.prepare_reminder(s, sid, str(args["customer_id"]))
                if out.get("has_due"):
                    events.append({"type": "reminder", **out})
                return out

            if name == "undo_last_transaction":
                confirmed_undo = bool(args.get("confirmed_undo", False))
                if confirmed_undo and self.undo_inspected_turn >= self.turn:
                    return {
                        "error": (
                            "GUARDRAIL: You cannot delete a confirmed transaction in the same turn you inspected it. "
                            "Read back the entry to the shopkeeper and ask 'Confirm delete?' first."
                        )
                    }
                out = await tools.undo_last_transaction(
                    s,
                    sid,
                    customer_id=str(args["customer_id"]) if args.get("customer_id") else None,
                    confirmed_undo=confirmed_undo,
                )
                if out.get("requires_confirmation"):
                    self.undo_inspected_turn = self.turn
                if out.get("undone"):
                    events.append({"type": "cancelled", **out})
                return out

            if name == "confirm_draft":
                did = str(args["draft_id"])
                # STRICT GUARDRAIL: A draft cannot be confirmed in the same turn it was created.
                created_turn = self.draft_turn.get(did, self.turn)
                if created_turn >= self.turn:
                    return {
                        "error": (
                            "GUARDRAIL: You cannot confirm a draft in the same turn it was created. "
                            "You must first read back the details to the shopkeeper and ask 'Confirm?'. "
                            "Only after they say yes in their next reply can you call confirm_draft."
                        )
                    }

                out = await tools.confirm_draft(s, sid, did, transcript_snippet=transcript)
                if out.get("confirmed"):
                    self.last_draft_id = None
                    events.append({"type": "confirmed", **out})
                return out

            if name == "record_cash_in":
                out = await tools.record_cash_in(
                    s,
                    sid,
                    amount=float(args["amount"]),
                    reason=args.get("reason", "deposit"),
                    description=args.get("description", ""),
                )
                if out.get("ok"):
                    events.append({"type": "cash_in", **out})
                return out

            if name == "record_cash_out":
                out = await tools.record_cash_out(
                    s,
                    sid,
                    amount=float(args["amount"]),
                    reason=args.get("reason", "expense"),
                    description=args.get("description", ""),
                )
                if out.get("ok"):
                    events.append({"type": "cash_out", **out})
                return out

            if name == "get_cash_balance":
                out = await tools.get_cash_balance(s, sid)
                if out.get("ok"):
                    events.append({"type": "cash_balance", **out})
                return out

            if name == "cancel_draft":
                out = await tools.cancel_draft(s, sid, str(args["draft_id"]))
                if out.get("cancelled"):
                    self.last_draft_id = None
                    events.append({"type": "cancelled", **out})
                return out

            return {"error": f"Unknown tool: {name}"}

        except Exception as e:
            log.exception("Tool execution %s failed", name)
            await s.rollback()
            return {"error": str(e)[:200]}
