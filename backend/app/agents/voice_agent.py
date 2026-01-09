# backend/app/agents/voice_agent.py
from __future__ import annotations

import os
import re
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from sqlalchemy.orm import Session

from app.config import settings
from app.models.call import Call
from app.models.data_packet import DataPacket
from app.models.lead import Lead
from app.services.openai_service import OpenAIService
from app.services.twilio_service import TwilioService
from app.utils.logger import logger
from app.utils.latency_tracker import LatencyTracker
from app.utils.response_cache import get_response_cache
from app.utils.quick_responses import try_quick_response
from app.utils.quality_tracker import get_quality_tracker

try:
    from twilio.twiml.voice_response import VoiceResponse, Gather
except Exception:
    VoiceResponse = None  # type: ignore
    Gather = None  # type: ignore


class ConversationPhase(Enum):
    OPENING = "opening"
    DISCOVERY = "discovery"
    PRESENTATION = "presentation"
    OBJECTION_HANDLING = "objection_handling"
    CLOSING = "closing"


class SalesState(Enum):
    STATE_0 = 0
    STATE_1 = 1
    STATE_2 = 2
    STATE_3 = 3
    STATE_4 = 4
    STATE_5 = 5
    STATE_6 = 6
    STATE_7 = 7
    STATE_8 = 8
    STATE_9 = 9
    STATE_10 = 10
    STATE_11 = 11
    STATE_12 = 12


class BANTScore:
    def __init__(self):
        self.budget = 0
        self.authority = 0
        self.need = 0
        self.timeline = 0
        self.overall = 0.0

    def calculate_overall(self) -> float:
        self.overall = (self.budget + self.authority + self.need + self.timeline) / 4.0
        return float(self.overall)

    def get_tier(self) -> str:
        if self.overall >= 75:
            return "hot_lead"
        if self.overall >= 50:
            return "warm_lead"
        if self.overall >= 30:
            return "cool_lead"
        return "cold_lead"


class _SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return ""


STATE_PROMPT_TEMPLATES: Dict[int, str] = {
    # (UNCHANGED: your templates exactly as provided)
    # ... keep your STATE_0..STATE_12 templates here ...
}

# NOTE: For brevity in this message, paste your existing templates block unchanged.
# (Do not modify template text unless you want to tighten constraints further.)


class VoiceAgent:
    _GLOBAL_CONVERSATION_STATES: Dict[int, Dict[str, Any]] = {}

    _RE_SPEAKER_LABEL_START = re.compile(r"(?im)^(?:\s*(?:agent|ai agent|assistant|lead|user)\s*:\s*)+")
    _RE_SPEAKER_LABEL_NEWLINE = re.compile(r"(?im)\n\s*(?:agent|ai agent|assistant|lead|user)\s*:\s*")
    _RE_AGENT_PREFIX = re.compile(r"(?im)^AGENT\s*:\s*")
    _RE_DOUBLE_AGENT = re.compile(r"\bAGENT:\s*AGENT:\s*", re.IGNORECASE)
    _RE_DOUBLE_LEAD = re.compile(r"\bLEAD:\s*LEAD:\s*", re.IGNORECASE)
    _RE_WHITESPACE = re.compile(r"[ \t]+")
    _RE_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

    _INTENT_NO_TIME = frozenset(["no time", "can't talk", "cant talk", "busy", "in a meeting", "call back later", "not now"])
    _INTENT_JUST_TELL = frozenset(["just tell me", "what do you want", "get to the point", "say it", "tell me what you want"])
    _INTENT_HOSTILE = frozenset(["stop calling", "don't call", "dont call", "remove me", "fuck", "f***", "leave me alone"])
    _INTENT_NOT_INTERESTED = frozenset(["not interested", "no interest", "no thanks", "don't need", "dont need", "we're good", "we are good"])
    _INTENT_TECH_ISSUE = frozenset(["can't hear", "cant hear", "hard to hear", "breaking up", "you are breaking up", "bad connection", "connection issue", "you're cutting out", "you are cutting out", "static", "echo", "speak up"])
    _INTENT_WHO_IS_THIS = frozenset(["who is this", "who are you", "what is this about", "what's this about", "what is this"])
    _INTENT_PERMISSION_YES = frozenset(["sure", "okay", "ok", "go ahead", "yeah", "yes", "yep", "fine", "a minute", "quickly"])
    _INTENT_PERMISSION_NO = frozenset(["no", "not now", "can't", "cant", "don't", "dont", "busy"])
    _INTENT_GUARDED = frozenset(["not sure", "hard to say", "depends", "maybe", "can't share", "cant share", "prefer not"])
    _INTENT_CONFIRM_YES = frozenset(["yes", "yeah", "yep", "correct", "right", "exactly"])
    _INTENT_RESONANCE = frozenset(["makes sense", "that's true", "exactly", "right", "we see that", "agreed"])
    _INTENT_HESITATION = frozenset(["maybe", "not sure", "need to think", "send info", "email me", "circle back", "later"])
    _INTENT_SCHEDULE = frozenset(["send invite", "calendar", "book", "schedule", "tomorrow", "next week", "monday", "tuesday", "wednesday", "thursday", "friday"])

    def __init__(self, db: Session):
        self.db = db
        self.twilio = TwilioService()
        self.openai = OpenAIService()

        self.twilio_say_voice = getattr(settings, "TWILIO_SAY_VOICE", None) or "alice"

        # ✅ FIX: cedar is not in your OpenAIService supported voices; use ash
        self.openai_tts_voice_forced = "ash"

        self.conversation_states = VoiceAgent._GLOBAL_CONVERSATION_STATES

    def _public_base_url(self) -> str:
        base = (getattr(settings, "TWILIO_WEBHOOK_URL", "") or "").strip()
        if not base:
            return ""
        if not base.endswith("/"):
            base += "/"
        return base

    def _should_use_openai_tts(self) -> bool:
        return bool(self._public_base_url()) and self.openai.is_tts_enabled()

    async def tts_audio_url(self, call_id: int, text: str) -> Optional[str]:
        if not self._should_use_openai_tts():
            return None

        text = (text or "").strip()
        if not text:
            return None

        import time
        tts_start = time.time()
        try:
            path = await self.openai.tts_to_file(
                text,
                voice=self.openai_tts_voice_forced,
                timeout_s=15.0,
            )
            tts_elapsed = (time.time() - tts_start) * 1000
            logger.info(f"[LATENCY] TTS generation for call_id={call_id}: {tts_elapsed:.2f}ms")
            filename = os.path.basename(path)
            return urljoin(self._public_base_url(), f"api/calls/{call_id}/tts/{filename}")
        except Exception as e:
            tts_elapsed = (time.time() - tts_start) * 1000
            logger.error(f"TTS generation failed (fallback to Twilio <Say>) after {tts_elapsed:.2f}ms: {e}")
            return None

    def _get_conversation_state(self, call_id: int) -> Dict[str, Any]:
        if call_id not in self.conversation_states:
            self.conversation_states[call_id] = {
                "sales_state": SalesState.STATE_0,
                "sales_state_entered_at": datetime.utcnow(),
                "sales_state_turns": 0,
                "sales_state_questions": 0,
                "phase": ConversationPhase.OPENING,
                "phase_start": datetime.utcnow(),
                "turn_count": 0,
                "bant": BANTScore(),
                "pain_points": [],
                "objections": [],
                "buying_signals": [],
                "sentiment_history": [],
                "questions_asked": {"situation": 0, "problem": 0, "implication": 0, "need_payoff": 0},
                "end_call": False,
                "audio_prompted": False,
                "audio_confirmed": False,
                "tech_issue_count": 0,
                "channel": "cold_call",
                "tone_profile": "neutral_curious",
                "account_context_loaded": False,
                "account_context": {},
            }
        return self.conversation_states[call_id]

    def _set_sales_state(self, state: Dict[str, Any], new_state: SalesState) -> None:
        if state.get("sales_state") == new_state:
            return
        state["sales_state"] = new_state
        state["sales_state_entered_at"] = datetime.utcnow()
        state["sales_state_turns"] = 0
        state["sales_state_questions"] = 0
        state["phase"] = self._map_state_to_phase(new_state)
        state["phase_start"] = datetime.utcnow()
        if new_state == SalesState.STATE_12:
            state["end_call"] = True

    def _map_state_to_phase(self, s: SalesState) -> ConversationPhase:
        if s in (SalesState.STATE_0, SalesState.STATE_1):
            return ConversationPhase.OPENING
        if s in (SalesState.STATE_2, SalesState.STATE_3, SalesState.STATE_4, SalesState.STATE_5):
            return ConversationPhase.DISCOVERY
        if s in (SalesState.STATE_6, SalesState.STATE_7):
            return ConversationPhase.PRESENTATION
        if s == SalesState.STATE_8:
            return ConversationPhase.OBJECTION_HANDLING
        return ConversationPhase.CLOSING

    def _infer_channel(self, lead: Optional[Lead], call: Optional[Call]) -> str:
        src = (getattr(lead, "source", "") or "").lower() if lead else ""
        if "inbound" in src:
            return "inbound"
        if "referral" in src or "warm" in src:
            return "warm_referral"
        return "cold_call"

    def _tone_profile_for_channel(self, channel: str) -> str:
        if channel == "inbound":
            return "helpful_direct"
        if channel == "warm_referral":
            return "warm_confident"
        return "neutral_curious"

    def _silent_context_load(self, lead: Lead, call: Call, state: Dict[str, Any]) -> None:
        if state.get("account_context_loaded"):
            return

        ctx = {
            "lead_name": lead.name,
            "lead_title": lead.title,
            "company": lead.company,
            "industry": getattr(lead, "company_industry", None),
            "company_size": getattr(lead, "company_size", None),
            "call_id": call.id,
            "lead_id": call.lead_id,
        }
        state["account_context"] = ctx
        state["account_context_loaded"] = True

        channel = self._infer_channel(lead, call)
        state["channel"] = channel
        state["tone_profile"] = self._tone_profile_for_channel(channel)

    def _strip_speaker_labels(self, text: str) -> str:
        if not text:
            return ""
        t = text.strip()
        t = self._RE_SPEAKER_LABEL_START.sub("", t)
        t = self._RE_SPEAKER_LABEL_NEWLINE.sub("\n", t)
        return t.strip()

    def append_to_call_transcript(self, call: Call, speaker: str, text: str, upsert_transcripts: bool = True, commit: bool = True) -> None:
        cleaned = self._strip_speaker_labels(text)
        if not cleaned:
            return
        existing = call.full_transcript or ""
        chunk = f"{speaker.upper()}: {cleaned}"
        call.full_transcript = (existing + "\n" + chunk).strip() if existing else chunk
        if commit:
            self.db.commit()

    def _build_opener(self, lead: Lead) -> str:
        name = (lead.name or "").strip() or "there"
        return f"Hi {name} — this is AADOS calling from Algonox. Did I catch you at a bad time?"

    def _detect_no_time(self, user_text: str) -> bool:
        t = (user_text or "").lower()
        return any(p in t for p in self._INTENT_NO_TIME)

    def _detect_hostile(self, user_text: str) -> bool:
        t = (user_text or "").lower()
        return any(p in t for p in self._INTENT_HOSTILE)

    def _detect_not_interested(self, user_text: str) -> bool:
        t = (user_text or "").lower()
        return any(p in t for p in self._INTENT_NOT_INTERESTED)

    def _detect_tech_issue(self, user_text: str) -> bool:
        t = (user_text or "").lower()
        return any(p in t for p in self._INTENT_TECH_ISSUE)

    def _detect_who_is_this(self, user_text: str) -> bool:
        t = (user_text or "").lower()
        return any(p in t for p in self._INTENT_WHO_IS_THIS)

    def _detect_permission_granted(self, user_text: str) -> bool:
        t = (user_text or "").lower().strip()
        if not t:
            return False
        return any(p in t for p in self._INTENT_PERMISSION_YES)

    def _detect_permission_denied(self, user_text: str) -> bool:
        t = (user_text or "").lower()
        return any(p in t for p in self._INTENT_PERMISSION_NO) and not self._detect_permission_granted(user_text)

    def _detect_guarded(self, user_text: str) -> bool:
        t = (user_text or "").strip()
        if not t:
            return True
        if len(t.split()) <= 2:
            return True
        return any(p in t.lower() for p in self._INTENT_GUARDED)

    def _detect_confirm_yes(self, user_text: str) -> bool:
        t = (user_text or "").lower().strip()
        return t in self._INTENT_CONFIRM_YES or "that's accurate" in t or "sounds right" in t

    def _detect_resonance(self, user_text: str) -> bool:
        t = (user_text or "").lower()
        return any(p in t for p in self._INTENT_RESONANCE)

    def _detect_hesitation(self, user_text: str) -> bool:
        t = (user_text or "").lower()
        return any(p in t for p in self._INTENT_HESITATION)

    def _detect_schedule_locked(self, user_text: str) -> bool:
        t = (user_text or "").lower()
        return any(p in t for p in self._INTENT_SCHEDULE)

    def _detect_objection(self, user_text: str) -> Optional[Dict[str, Any]]:
        text_lower = (user_text or "").lower()
        if any(w in text_lower for w in ["expensive", "cost", "budget", "afford", "price", "pricing"]):
            return {"type": "price", "text": user_text}
        if any(w in text_lower for w in ["not now", "later", "next quarter", "need time", "think about", "follow up later"]):
            return {"type": "timing", "text": user_text}
        if any(w in text_lower for w in ["talk to", "check with", "boss", "manager", "leadership", "team needs"]):
            return {"type": "authority", "text": user_text}
        if any(w in text_lower for w in ["using", "already have", "competitor", "another tool", "other solution", "we use"]):
            return {"type": "competition", "text": user_text}
        return None

    def _detect_buying_signals(self, user_text: str) -> List[str]:
        text_lower = (user_text or "").lower()
        signals: List[str] = []
        if any(w in text_lower for w in ["how does", "when can", "what's next", "what is next", "how do we start", "show me"]):
            signals.append("next_steps_inquiry")
        if any(w in text_lower for w in ["pricing", "cost", "how much", "investment"]):
            signals.append("pricing_inquiry")
        if any(w in text_lower for w in ["sounds good", "interested", "makes sense", "like this"]):
            signals.append("positive_sentiment")
        return signals

    def _update_bant_scores(self, state: Dict[str, Any], user_text: str):
        text_lower = (user_text or "").lower()
        bant: BANTScore = state["bant"]

        if any(w in text_lower for w in ["budget", "allocated", "spend", "cost", "$", "usd"]):
            if any(w in text_lower for w in ["100k", "150k", "200k"]):
                bant.budget = max(bant.budget, 80)
            else:
                bant.budget = max(bant.budget, 55)

        if any(w in text_lower for w in ["i decide", "my decision", "i approve", "i can sign", "i own"]):
            bant.authority = max(bant.authority, 85)
        elif any(w in text_lower for w in ["vp", "director", "head of", "founder", "ceo"]):
            bant.authority = max(bant.authority, 70)
        elif any(w in text_lower for w in ["talk to my", "check with", "need approval"]):
            bant.authority = max(bant.authority, 35)

        pain_point_count = len(state.get("pain_points", []))
        if pain_point_count >= 3:
            bant.need = max(bant.need, 88)
        elif pain_point_count >= 2:
            bant.need = max(bant.need, 70)
        elif pain_point_count >= 1:
            bant.need = max(bant.need, 50)

        if any(w in text_lower for w in ["urgent", "asap", "this month", "this quarter", "immediately"]):
            bant.timeline = max(bant.timeline, 85)
        elif any(w in text_lower for w in ["soon", "next quarter", "planning", "next month"]):
            bant.timeline = max(bant.timeline, 65)

        bant.calculate_overall()

    def _transcript_tail(self, call: Call, limit: int = 800) -> str:
        return (call.full_transcript or "")[-limit:]

    def _build_state_prompt(
        self,
        *,
        sales_state: SalesState,
        call: Call,
        lead: Lead,
        data_packet: Optional[DataPacket],
        user_input: str,
        state: Dict[str, Any],
        last_objection_type: str,
        last_buying_signal: str,
    ) -> str:
        template = STATE_PROMPT_TEMPLATES.get(int(sales_state.value), "")
        tone = state.get("tone_profile") or "neutral_curious"
        channel = state.get("channel") or "cold_call"

        params = _SafeFormatDict(
            lead_name=(lead.name or "").strip() or "there",
            lead_title=(lead.title or "").strip() or "your role",
            lead_company=(lead.company or "").strip() or "your company",
            lead_industry=(getattr(lead, "company_industry", "") or "").strip() or "Unknown",
            channel=channel,
            tone_profile=tone,
            transcript_tail=self._transcript_tail(call),
            user_input=(user_input or "").strip(),
            previous_state_id=str(state.get("sales_state", SalesState.STATE_0).value),
            state_turn_count=int(state.get("sales_state_turns", 0)),
            state_question_count=int(state.get("sales_state_questions", 0)),
            detected_objection_type=last_objection_type or "none",
            last_buying_signal=last_buying_signal or "none",
            detected_not_interested="",
            detected_no_time="",
            detected_hostile="",
        )
        try:
            return template.format_map(params).strip()
        except Exception:
            return template.strip()

    def _route_state_before_reply(self, cur: SalesState, user_text: str, state: Dict[str, Any]) -> SalesState:
        if state.get("end_call"):
            return SalesState.STATE_12

        if cur == SalesState.STATE_2 and int(state.get("sales_state_questions", 0)) >= 2:
            return SalesState.STATE_3

        if cur == SalesState.STATE_0:
            if not state.get("audio_prompted"):
                return SalesState.STATE_0
            if state.get("audio_prompted") and not state.get("audio_confirmed"):
                return SalesState.STATE_1
            return SalesState.STATE_1

        if cur == SalesState.STATE_1:
            if self._detect_permission_granted(user_text):
                return SalesState.STATE_2
            return SalesState.STATE_1

        if cur == SalesState.STATE_3:
            if self._detect_guarded(user_text):
                return SalesState.STATE_3
            if int(state.get("sales_state_turns", 0)) >= 1:
                return SalesState.STATE_4
            return SalesState.STATE_3

        if cur == SalesState.STATE_4:
            if self._detect_confirm_yes(user_text):
                return SalesState.STATE_5
            return SalesState.STATE_3

        if cur == SalesState.STATE_5:
            return SalesState.STATE_6

        if cur == SalesState.STATE_6:
            if self._detect_not_interested(user_text):
                return SalesState.STATE_12
            if self._detect_objection(user_text):
                return SalesState.STATE_8
            if self._detect_resonance(user_text):
                return SalesState.STATE_7
            return SalesState.STATE_6

        if cur == SalesState.STATE_7:
            if self._detect_not_interested(user_text):
                return SalesState.STATE_12
            if self._detect_objection(user_text):
                return SalesState.STATE_8
            if any(w in (user_text or "").lower() for w in ["who else", "procurement", "security", "approval", "sign off", "signoff", "legal"]):
                return SalesState.STATE_9
            if any(w in (user_text or "").lower() for w in ["demo", "meeting", "calendar", "schedule", "invite", "send times"]):
                return SalesState.STATE_11
            return SalesState.STATE_7

        if cur == SalesState.STATE_8:
            if self._detect_not_interested(user_text):
                return SalesState.STATE_12
            if int(state.get("sales_state_turns", 0)) >= 1 and not self._detect_objection(user_text):
                return SalesState.STATE_11
            return SalesState.STATE_8

        if cur == SalesState.STATE_9:
            if self._detect_hesitation(user_text):
                return SalesState.STATE_10
            return SalesState.STATE_11

        if cur == SalesState.STATE_10:
            if self._detect_permission_granted(user_text) or any(p in (user_text or "").lower() for p in ["yes", "okay", "sure"]):
                return SalesState.STATE_11
            return SalesState.STATE_12

        if cur == SalesState.STATE_11:
            if self._detect_schedule_locked(user_text):
                return SalesState.STATE_12
            if self._detect_not_interested(user_text):
                return SalesState.STATE_12
            return SalesState.STATE_11

        return cur

    # -----------------------------
    # ✅ NEW: Realtime path instruction builder (NO LLM CALL)
    # -----------------------------
    def build_realtime_instructions(self, call: Call, user_input: str) -> Dict[str, Any]:
        """
        Returns:
          {
            "instructions": str,   # send to OpenAI Realtime response.create
            "end_call": bool
          }
        This reuses your exact state machine + guardrails, but does not call chat.completions.
        """
        lead = self.db.query(Lead).filter(Lead.id == call.lead_id).first()
        packet = self.db.query(DataPacket).filter(DataPacket.lead_id == call.lead_id).first()

        if not lead:
            return {"instructions": "Politely say thanks for the time and end the call.", "end_call": True}

        state = self._get_conversation_state(call.id)
        self._silent_context_load(lead, call, state)

        state["turn_count"] = int(state.get("turn_count", 0)) + 1

        # Hard interrupts (deterministic)
        if self._detect_hostile(user_input):
            self._set_sales_state(state, SalesState.STATE_12)
            return {"instructions": "Say exactly: Understood—sorry to bother you. I’ll remove you from our list. Have a good day.", "end_call": True}

        if self._detect_tech_issue(user_input):
            state["tech_issue_count"] = int(state.get("tech_issue_count", 0)) + 1
            if state["tech_issue_count"] <= 1:
                return {"instructions": "Say exactly: Sorry—you’re breaking up a bit. Can you hear me clearly?", "end_call": False}
            self._set_sales_state(state, SalesState.STATE_12)
            return {"instructions": "Say exactly: No worries—seems like the connection isn’t great. I’ll let you go. Have a good day.", "end_call": True}

        if self._detect_not_interested(user_input):
            self._set_sales_state(state, SalesState.STATE_12)
            return {"instructions": "Say exactly: Totally fair—thanks for the quick response. I’ll let you go.", "end_call": True}

        if any(w in (user_input or "").lower() for w in ["bye", "goodbye", "stop calling"]):
            self._set_sales_state(state, SalesState.STATE_12)
            return {"instructions": "Say exactly: Understood. Thanks for your time, and have a great day.", "end_call": True}

        cur_state: SalesState = state.get("sales_state", SalesState.STATE_0)

        # STATE_0 who-is-this
        if cur_state == SalesState.STATE_0 and self._detect_who_is_this(user_input):
            company = (lead.company or "").strip() or "your company"
            title = (lead.title or "").strip() or "your role"
            forced = f"This is AADOS from Algonox—I'm reaching out because you're listed as {title} at {company}. Did I catch you at a bad time?"
            return {"instructions": f"Say exactly: {forced}", "end_call": False}

        # STATE_0 audio confirmation gate
        if cur_state == SalesState.STATE_0 and not state.get("audio_prompted"):
            state["audio_prompted"] = True
            return {"instructions": "Say exactly: Before we continue—can you hear me clearly?", "end_call": False}

        if cur_state == SalesState.STATE_0 and state.get("audio_prompted") and not state.get("audio_confirmed"):
            if any(p in (user_input or "").lower() for p in ["no", "can't", "cant", "not really", "hard to hear"]):
                state["tech_issue_count"] = int(state.get("tech_issue_count", 0)) + 1
                if state["tech_issue_count"] <= 1:
                    return {"instructions": "Say exactly: Got it—let me try again. Can you hear me now?", "end_call": False}
                self._set_sales_state(state, SalesState.STATE_12)
                return {"instructions": "Say exactly: No worries—I'll let you go and try another time. Have a good day.", "end_call": True}
            state["audio_confirmed"] = True

        if self._detect_no_time(user_input):
            self._set_sales_state(state, SalesState.STATE_12)
            email = (getattr(lead, "email", "") or "").strip()
            if email:
                return {"instructions": f"Say exactly: No worries—I’ll send a short note to {email} and let you go. Thanks for your time.", "end_call": True}
            return {"instructions": "Say exactly: No worries—I’ll send a short note and let you go. Thanks for your time.", "end_call": True}

        signals = self._detect_buying_signals(user_input)
        last_buy_signal = signals[-1] if signals else ""
        objection = self._detect_objection(user_input)
        last_objection_type = objection.get("type") if objection else ""
        if objection:
            state["objections"].append(objection)
        if signals:
            state["buying_signals"].extend(signals)

        self._update_bant_scores(state, user_input)
        if any(w in (user_input or "").lower() for w in ["challenge", "problem", "difficult", "frustrating", "slow", "manual", "pain", "issue"]):
            state["pain_points"].append(user_input)

        cur_state = state.get("sales_state", SalesState.STATE_0)
        speak_state = self._route_state_before_reply(cur_state, user_input, state)
        self._set_sales_state(state, speak_state)

        if speak_state == SalesState.STATE_1 and self._detect_permission_denied(user_input) and not self._detect_permission_granted(user_input):
            self._set_sales_state(state, SalesState.STATE_12)
            return {"instructions": "Say exactly: No problem at all—thanks for your time. I’ll let you go.", "end_call": True}

        prompt = self._build_state_prompt(
            sales_state=speak_state,
            call=call,
            lead=lead,
            data_packet=packet,
            user_input=user_input,
            state=state,
            last_objection_type=last_objection_type,
            last_buying_signal=last_buy_signal,
        )

        # Strong runtime constraints for realtime speaking (matches your postprocess behavior)
        prompt += (
            "\n\nOUTPUT RULES (strict):\n"
            "- 1 to 2 sentences max\n"
            "- At most ONE question\n"
            "- No bullet points\n"
            "- No re-introductions\n"
            "- Keep it under ~12 seconds of speech\n"
        )

        # We consider that the agent will speak one turn now
        state["sales_state_turns"] = int(state.get("sales_state_turns", 0)) + 1

        return {"instructions": prompt, "end_call": bool(state.get("end_call", False))}

    # -----------------------------
    # EXISTING TwiML builders + generate_reply remain unchanged below
    # (Paste the rest of your existing file from build_initial_twiml onward unchanged.)
    # -----------------------------

    def build_initial_twiml(self, call_id: int, opener_text: str, opener_audio_url: Optional[str]) -> str:
        if VoiceResponse is None or Gather is None:
            return "<Response></Response>"

        vr = VoiceResponse()
        gather = Gather(
            input="speech",
            action=f"/api/calls/{call_id}/webhook/turn",
            method="POST",
            timeout=6,
            speech_timeout="auto",
            barge_in=True,
        )

        if opener_audio_url:
            gather.play(opener_audio_url)
        else:
            gather.say(opener_text, voice=self.twilio_say_voice)

        vr.append(gather)
        vr.say("I didn't catch that. Thanks for your time. Goodbye.", voice=self.twilio_say_voice)
        vr.hangup()
        return str(vr)

    def build_turn_twiml(self, call_id: int, agent_text: str, agent_audio_url: Optional[str]) -> str:
        if VoiceResponse is None or Gather is None:
            return "<Response></Response>"

        state = self._get_conversation_state(call_id)
        vr = VoiceResponse()

        if state.get("end_call"):
            if agent_audio_url:
                vr.play(agent_audio_url)
            else:
                vr.say(agent_text if agent_text else "Okay.", voice=self.twilio_say_voice)
            vr.hangup()
            return str(vr)

        gather = Gather(
            input="speech",
            action=f"/api/calls/{call_id}/webhook/turn",
            method="POST",
            timeout=6,
            speech_timeout="auto",
            barge_in=True,
        )

        if agent_audio_url:
            gather.play(agent_audio_url)
        else:
            gather.say(agent_text if agent_text else "Okay.", voice=self.twilio_say_voice)

        vr.append(gather)
        vr.say("Thanks for your time. Goodbye.", voice=self.twilio_say_voice)
        vr.hangup()
        return str(vr)

    async def initiate_outbound_call(self, lead: Lead, call: Call) -> Optional[str]:
        """
        Initiate an outbound call to a lead using Twilio.

        Args:
            lead: Lead object with contact information
            call: Call object that was created in the database

        Returns:
            Twilio Call SID if successful, None otherwise
        """
        try:
            phone_number = lead.phone or call.phone_number
            if not phone_number:
                raise ValueError("No phone number available for lead")

            # Build the webhook callback URL
            callback_path = f"/api/calls/{call.id}/webhook"

            logger.info(f"Initiating outbound call to {phone_number} for lead {lead.id}, call {call.id}")

            # Make the call via Twilio
            twilio_call = await self.twilio.make_call(
                to_number=phone_number,
                callback_path=callback_path
            )

            if twilio_call and hasattr(twilio_call, 'sid'):
                logger.info(f"Twilio call created successfully: SID={twilio_call.sid}")
                return twilio_call.sid
            else:
                logger.error("Twilio call creation returned no SID")
                return None

        except Exception as e:
            logger.exception(f"Failed to initiate outbound call for lead {lead.id}: {e}")
            raise
