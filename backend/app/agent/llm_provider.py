"""Unified LLMProvider Interface supporting Gemini 2.5 Flash with strict Tool/Function Calling.

Provides an abstract interface and concrete implementations:
- GeminiLLMProvider (Google GenAI / Gemini 2.5 Flash)
- MockRuleBasedLLMProvider (Offline / zero-key testing fallback)
"""
import abc
import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx

from ..config import settings

log = logging.getLogger("dukaan.agent.llm")


class LLMResponse:
    def __init__(
        self,
        text: str = "",
        function_calls: Optional[List[Dict[str, Any]]] = None,
        raw: Any = None,
        raw_parts: Optional[List[Any]] = None,
    ):
        self.text = text
        self.function_calls = function_calls or []
        self.raw = raw
        self.raw_parts = raw_parts or []


class BaseLLMProvider(abc.ABC):
    """Abstract interface for LLM Orchestrator providers."""

    @abc.abstractmethod
    async def chat_turn(
        self,
        history: List[Dict[str, Any]],
        tools_declarations: List[Dict[str, Any]],
        system_instruction: str,
    ) -> LLMResponse:
        """Process one conversational turn given history and available tools."""
        pass


class GeminiLLMProvider(BaseLLMProvider):
    """Gemini Flash implementation via google-genai or direct Google REST API."""

    def __init__(self, api_key: str, model_name: str = "gemini-3-flash-preview"):
        self.api_key = api_key
        # Automatically map legacy/unavailable flash model strings to available gemini-3-flash-preview
        if "2.5-flash" in model_name or "2.0-flash" in model_name or "1.5-flash" in model_name:
            self.model_name = "gemini-3-flash-preview"
        else:
            self.model_name = model_name
        self._genai_client = None

        # Check if google.genai SDK is available
        try:
            from google import genai
            self._genai_client = genai.Client(api_key=api_key)
            log.info("Initialized GeminiLLMProvider using google-genai SDK (model: %s)", self.model_name)
        except Exception as e:
            log.info("google-genai SDK not available or failed (%s); using HTTP REST fallback for Gemini", e)

    async def chat_turn(
        self,
        history: List[Dict[str, Any]],
        tools_declarations: List[Dict[str, Any]],
        system_instruction: str,
    ) -> LLMResponse:
        # Use direct Google Gemini REST API with thoughtSignature preservation
        try:
            return await self._call_gemini_rest(history, tools_declarations, system_instruction)
        except Exception as rest_err:
            log.warning("Gemini REST API error (%s); falling back to rule-based Kirana agent", rest_err)
            return await MockRuleBasedLLMProvider().chat_turn(history, tools_declarations, system_instruction)

    async def _call_gemini_rest(
        self,
        history: List[Dict[str, Any]],
        tools_declarations: List[Dict[str, Any]],
        system_instruction: str,
    ) -> LLMResponse:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"

        # Build payload according to Gemini REST specification
        rest_contents = []
        for h in history:
            role = "model" if h.get("role") in ("model", "assistant") else "user"
            parts = []
            for p in h.get("parts", []):
                if isinstance(p, dict):
                    if "functionCall" in p:
                        # Full dict preserving thoughtSignature and call ID
                        parts.append(p)
                    elif "functionResponse" in p:
                        parts.append(p)
                    elif "text" in p:
                        parts.append({"text": p["text"]})
                    elif "function_call" in p:
                        fc = p["function_call"]
                        parts.append({"functionCall": {"name": fc["name"], "args": fc.get("args", {})}})
                    elif "function_response" in p:
                        fr = p["function_response"]
                        parts.append({"functionResponse": {"name": fr["name"], "response": fr.get("response", {})}})
                else:
                    if hasattr(p, "text") and p.text:
                        parts.append({"text": p.text})
                    elif hasattr(p, "function_call") and p.function_call:
                        parts.append({"functionCall": {"name": p.function_call.name, "args": dict(p.function_call.args or {})}})
                    elif hasattr(p, "function_response") and p.function_response:
                        parts.append({"functionResponse": {"name": p.function_response.name, "response": p.function_response.response}})
            if parts:
                rest_contents.append({"role": role, "parts": parts})

        payload = {
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "contents": rest_contents,
            "tools": [{"functionDeclarations": tools_declarations}],
            "generationConfig": {"temperature": 0.2},
        }

        # Fast timeout with smart retry and candidate models
        candidate_models = ["gemini-3-flash-preview", "gemini-3.1-flash-lite", "gemini-3.1-flash-lite-preview"]
        if self.model_name not in candidate_models:
            candidate_models.insert(0, self.model_name)

        last_err = None
        for model in candidate_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
            for attempt in range(2):  # Quick 2 attempts per model (handles momentary 503 spikes)
                try:
                    async with httpx.AsyncClient(timeout=4.5) as client:
                        res = await client.post(url, json=payload)
                        if res.status_code == 200:
                            data = res.json()
                            candidates = data.get("candidates", [])
                            if not candidates:
                                return LLMResponse(text="Sorry, could not generate a response.")

                            parts = candidates[0].get("content", {}).get("parts", [])
                            text_str = "".join(p.get("text", "") for p in parts if "text" in p).strip()
                            fcalls = [
                                {"name": p["functionCall"]["name"], "args": p["functionCall"].get("args", {})}
                                for p in parts
                                if "functionCall" in p
                            ]
                            return LLMResponse(text=text_str, function_calls=fcalls, raw=data, raw_parts=parts)
                        elif res.status_code == 503:
                            log.warning("Gemini model %s returned 503 (attempt %d/2); retrying...", model, attempt + 1)
                            await asyncio.sleep(0.3)
                        else:
                            log.warning("Gemini REST error %s: %s", res.status_code, res.text[:100])
                            break
                except (httpx.TimeoutException, httpx.RequestError) as net_err:
                    log.warning("Gemini connection/timeout on %s (attempt %d/2): %s", model, attempt + 1, net_err)
                    last_err = net_err
                    await asyncio.sleep(0.2)

        if last_err:
            raise last_err
        raise RuntimeError("All Gemini models temporarily unavailable")


class MockRuleBasedLLMProvider(BaseLLMProvider):
    """Offline / testing versatile rule-based agent simulator for Kirana transactions."""

    async def chat_turn(
        self,
        history: List[Dict[str, Any]],
        tools_declarations: List[Dict[str, Any]],
        system_instruction: str,
    ) -> LLMResponse:
        # Check last user message
        user_text = ""
        for msg in reversed(history):
            if msg.get("role") == "user":
                for p in msg.get("parts", []):
                    if isinstance(p, dict) and "text" in p:
                        user_text = p["text"]
                        break
                if user_text:
                    break

        lower = user_text.lower()

        # Check if confirm_draft or cancel_draft was just executed
        for msg in history:
            for p in msg.get("parts", []):
                if isinstance(p, dict) and "function_response" in p:
                    fr = p["function_response"]
                    if fr.get("name") == "confirm_draft":
                        c_res = (fr.get("response") or {}).get("result", {})
                        if c_res.get("confirmed"):
                            return LLMResponse(text=f"Confirmed! Recorded in ledger. Updated balance is ₹{c_res.get('new_balance', 0):,.2f}.")
                    elif fr.get("name") == "cancel_draft":
                        return LLMResponse(text="The draft has been cancelled.")

        # Check for confirmation
        confirm_words = ["haan", "houdu", "haudu", "sari", "yes", "confirm", "theek", "ok", "karein", "done", "maadi"]
        cancel_words = ["nahi", "beda", "illa", "no", "cancel", "galat", "hatao"]

        # Check if previous turn returned a draft creation response
        last_draft_id = None
        last_draft_info = {}
        for msg in history:
            for p in msg.get("parts", []):
                if isinstance(p, dict) and "function_response" in p:
                    fr = p["function_response"]
                    if fr.get("name") == "create_draft":
                        last_draft_info = (fr.get("response") or {}).get("result", {})
                        last_draft_id = last_draft_info.get("draft_id")

        if any(w in lower for w in confirm_words) and last_draft_id:
            return LLMResponse(
                text="",
                function_calls=[{"name": "confirm_draft", "args": {"draft_id": last_draft_id}}],
            )

        if any(w in lower for w in cancel_words) and last_draft_id:
            return LLMResponse(
                text="",
                function_calls=[{"name": "cancel_draft", "args": {"draft_id": last_draft_id}}],
            )

        # Check for Shop Summary queries
        if any(w in lower for w in ["summary", "total udhar", "collection", "aaj ka", "aaj kitna", "dukaan ka"]):
            # Check if get_shop_summary response is already in history
            for msg in history:
                for p in msg.get("parts", []):
                    if isinstance(p, dict) and "function_response" in p:
                        fr = p["function_response"]
                        if fr.get("name") == "get_shop_summary":
                            res = (fr.get("response") or {}).get("result", {})
                            tot = res.get("total_outstanding", 0)
                            cr = res.get("credit_today", 0)
                            pay = res.get("payments_today", 0)
                            cnt = res.get("customer_count", 0)
                            return LLMResponse(
                                text=f"Dukaan summary: Total outstanding is ₹{tot:,.2f} across {cnt} customers. Today: ₹{cr:,.2f} credit given, ₹{pay:,.2f} payments collected."
                            )
            return LLMResponse(
                text="",
                function_calls=[{"name": "get_shop_summary", "args": {}}],
            )

        # Check for Balance inquiry response already in history
        for msg in history:
            for p in msg.get("parts", []):
                if isinstance(p, dict) and "function_response" in p:
                    fr = p["function_response"]
                    if fr.get("name") == "get_balance":
                        b_res = (fr.get("response") or {}).get("result", {})
                        cname = b_res.get("customer", "Customer")
                        cbal = b_res.get("balance", 0)
                        return LLMResponse(text=f"{cname}'s current balance is ₹{cbal:,.2f}.")

        # Check for balance inquiry prompt
        if any(w in lower for w in ["balance", "eshtu", "kitna baaki", "hisab"]):
            # Check if customer search response already in history
            for msg in history:
                for p in msg.get("parts", []):
                    if isinstance(p, dict) and "function_response" in p:
                        fr = p["function_response"]
                        if fr.get("name") == "search_customers":
                            matches = (fr.get("response") or {}).get("result", {}).get("matches", [])
                            if matches:
                                return LLMResponse(
                                    text="",
                                    function_calls=[{"name": "get_balance", "args": {"customer_id": matches[0]["customer_id"]}}],
                                )
                            return LLMResponse(text="No customer found with that name.")
            words = [w for w in re.sub(r"[^\w\s]", "", user_text).split() if len(w) > 2 and w.lower() not in ("balance", "eshtu", "kitna", "baaki", "hisab", "karo", "batao", "ka", "ki", "ge")]
            if not words:
                return LLMResponse(text="Which customer's balance would you like to check?")
            return LLMResponse(
                text="",
                function_calls=[{"name": "search_customers", "args": {"name": words[0]}}],
            )

        # Look for numbers (digits or spoken Hindi/Kannada/English phrases)
        from .indian_numbers import extract_indian_amount
        amount = extract_indian_amount(user_text)

        # Look for transaction type
        is_credit = any(w in lower for w in ["udhar", "baaki", "bardu", "likho", "credit", "saala", "kadan", "appu"])
        is_payment = any(w in lower for w in ["jama", "kotta", "diya", "paid", "received", "vasool", "chukaya", "varavu"])

        # Check if customer search was done in previous round
        searched_matches = None
        new_customer_created = None
        for msg in history:
            for p in msg.get("parts", []):
                if isinstance(p, dict) and "function_response" in p:
                    fr = p["function_response"]
                    if fr.get("name") == "search_customers":
                        searched_matches = (fr.get("response") or {}).get("result", {}).get("matches", [])
                    elif fr.get("name") == "create_customer":
                        new_customer_created = (fr.get("response") or {}).get("result", {})
                    elif fr.get("name") == "create_draft":
                        dr = (fr.get("response") or {}).get("result", {})
                        if "draft_id" in dr:
                            return LLMResponse(
                                text=f"Recorded ₹{dr.get('amount')} {dr.get('type')} for {dr.get('customer')}. Confirm?"
                            )

        # If a new customer was just created, immediately draft the transaction!
        if new_customer_created and "customer_id" in new_customer_created and amount and (is_credit or is_payment):
            tx_type = "credit" if is_credit else "payment"
            return LLMResponse(
                text="",
                function_calls=[{
                    "name": "create_draft",
                    "args": {
                        "customer_id": new_customer_created["customer_id"],
                        "type": tx_type,
                        "amount": amount,
                        "note": "New customer voice entry",
                    }
                }],
            )

        # If name and amount found
        if amount and (is_credit or is_payment):
            tx_type = "credit" if is_credit else "payment"
            # Extract name (first word that isn't a stopword)
            stopwords = {"ge", "ka", "ki", "ne", "ko", "rupayi", "rupaye", "rs", "inr", "udhar", "jama", "bardu", "likho", "kotta", "diya", "paid", "add", "credit", "bantu", "daal", "do", "kadan", "appu"}
            tokens = [w for w in re.sub(r"[^\w\s]", "", user_text).split() if w.lower() not in stopwords and not w.isdigit()]
            cust_name = tokens[0].capitalize() if tokens else "Customer"

            if searched_matches is not None:
                if len(searched_matches) == 1:
                    target = searched_matches[0]
                    return LLMResponse(
                        text="",
                        function_calls=[{
                            "name": "create_draft",
                            "args": {
                                "customer_id": target["customer_id"],
                                "type": tx_type,
                                "amount": amount,
                                "note": "Voice entry",
                            }
                        }],
                    )
                elif len(searched_matches) > 1:
                    summary = " and ".join(f"{m['name']} ({m.get('landmark', '')})" for m in searched_matches[:2])
                    return LLMResponse(text=f"Found multiple matches: {summary}. Which customer do you mean?")
                else:
                    # ZERO MATCHES: Automatically create the new customer!
                    return LLMResponse(
                        text="",
                        function_calls=[{"name": "create_customer", "args": {"name": cust_name}}],
                    )
            else:
                return LLMResponse(
                    text="",
                    function_calls=[{"name": "search_customers", "args": {"name": cust_name}}],
                )

        # If casual shop-floor chatter / browsing without an amount or khata command, remain silent!
        casual_phrases = ["lena hai", "dena", "kaunsa", "marigold", "parle", "chahiye", "kitne ka", "hai kya", "kya hai", "aur kuch", "theek", "acha", "bhaiya"]
        if any(w in lower for w in casual_phrases) and not amount:
            return LLMResponse(text="[SILENT]")

        # Explicit greeting on initial turn (strict word boundary)
        if re.search(r"\b(?:namaste|namaskar|namaskara|hello|hi|vanakkam)\b", lower) and len(history) <= 2:
            return LLMResponse(text="Namaste! Dukaan Khata active hai. Kiska hisaab likhna hai?")

        # Contextual clarify if customer name was provided without amount
        stopwords = {"ge", "ka", "ki", "ko", "ne", "rupayi", "rupaye", "rs", "inr", "udhar", "jama", "bardu", "likho", "kotta", "diya", "paid", "add", "credit", "bantu", "daal", "do", "kadan", "appu"}
        tokens = [w for w in re.sub(r"[^\w\s]", "", user_text).split() if w.lower() not in stopwords and not w.isdigit()]
        if tokens and not amount:
            name = tokens[0].capitalize()
            return LLMResponse(text=f"{name} ke naam kitna udhar ya payment likhna hai?")

        # Contextual clarify if amount was provided without customer name
        if amount and not tokens:
            return LLMResponse(text=f"₹{amount:,.0f} kiske naam likhna hai? Kripya customer ka naam batayein.")

        # Default fallback: Never repeat boilerplate greeting! Ask politely to repeat
        return LLMResponse(text="Samajh nahi aaya, kripya dobara bolein.")


def get_llm_provider() -> BaseLLMProvider:
    """Factory creating configured LLMProvider (Gemini 2.5 Flash or Mock fallback)."""
    if settings.gemini_api_key and settings.gemini_api_key.strip():
        return GeminiLLMProvider(api_key=settings.gemini_api_key, model_name=settings.gemini_model)
    log.info("No GEMINI_API_KEY provided; using MockRuleBasedLLMProvider for offline testing")
    return MockRuleBasedLLMProvider()

