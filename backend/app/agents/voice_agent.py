# backend/app/agents/voice_agent.py
"""
VoiceAgent (FRD + STATE_0/STATE_1 aligned)
- SPIN-based flow with ConversationPhase tracking
- BANT scoring + call metadata updates
- Objection + buying-signal detection
- ✅ OpenAI TTS integration (voice forced to "cedar") for Twilio (<Play> inside <Gather>) with fallback to Twilio <Say>
- ✅ STATE_1 enforcement (Permission + Clear Exit + Micro-Agenda + Context Hook) as a deterministic step
- ✅ Prompt guardrails to avoid:
  - "This is <LEAD NAME> calling..." (wrong identity)
  - Repeating "Hi <Name>" every turn
  - Re-introducing the caller every message
"""

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

try:
    from twilio.twiml.voice_response import VoiceResponse, Gather
except Exception:
    VoiceResponse = None  # type: ignore
    Gather = None  # type: ignore


# -----------------------------
# Legacy conversation phases (kept for existing analytics fields)
# -----------------------------
class ConversationPhase(Enum):
    OPENING = "opening"                 # STATE_0 + STATE_1
    DISCOVERY = "discovery"             # STATE_2..STATE_5
    PRESENTATION = "presentation"       # STATE_6..STATE_7
    OBJECTION_HANDLING = "objection_handling"  # STATE_8
    CLOSING = "closing"                 # STATE_9..STATE_12


# -----------------------------
# Control-plane conversation states (0..12)
# -----------------------------
class SalesState(Enum):
    STATE_0 = 0   # Call start / audio+identity / safe opener handling
    STATE_1 = 1   # Permission + clear exit + micro-agenda + context hook
    STATE_2 = 2   # Safe entry discovery (max 2 questions)
    STATE_3 = 3   # Earned depth discovery
    STATE_4 = 4   # Problem confirmation (label + confirm)
    STATE_5 = 5   # Quantification / impact sizing
    STATE_6 = 6   # Reframe with insight
    STATE_7 = 7   # Solution mapping (tie to pain)
    STATE_8 = 8   # Objection handling
    STATE_9 = 9   # Authority / process mapping
    STATE_10 = 10 # Risk reversal / de-risk next step
    STATE_11 = 11 # Close for calendar next step
    STATE_12 = 12 # Exit (polite end)


# -----------------------------
# BANT (kept)
# -----------------------------
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


# -----------------------------
# STATE prompts (from Claude output file prompt_cl.txt)
# -----------------------------
STATE_PROMPT_TEMPLATES: Dict[int, str] = {
    0: '''You are AADOS, a voice agent from Algonox calling {lead_name} at {lead_company} ({lead_industry}).

Context:
- Channel: {channel}
- Tone profile: {tone_profile}
- Call transcript so far: {transcript_tail}
- Prospect's last message: {user_input}

STATE_0 OBJECTIVE:
The opener has already been played. Your job now is to:
1. Confirm the prospect heard the opener correctly (brief, no re-greeting)
2. If they seem confused or asked "who is this," clarify: "This is AADOS from Algonox — we work with companies like {lead_company} on {lead_industry} operations."
3. Get a micro-acknowledgment ("okay", "sure", "yeah") so we can move to asking for time.

Respond in 1–2 sentences. Ask no more than 1 question (usually just a confirmation). 
No bullet points. Do not mention product, features, or pricing.
Do not assume they're ready to engage — just confirm they're listening and willing to hear more.

Guardrail: You are AADOS from Algonox. Never pretend to be {lead_name}. Keep it brief and conversational.

Output: One short turn. Then wait for their response.''',
    1: '''You are AADOS from Algonox calling {lead_name} at {lead_company} ({lead_industry}).

Context:
- Channel: {channel}
- Tone: {tone_profile}
- Prospect: {lead_name}, {lead_title}
- Recent exchange: {transcript_tail}
- Their last message: {user_input}
- This is turn #{state_turn_count} in STATE_1

STATE_1 OBJECTIVE:
Ask for explicit time permission and set a credible, brief micro-agenda. Make it safe to say no.

Required:
1. Request a specific short duration (3–5 min if cold call, adapt if warm/inbound)
2. Offer an escape hatch: "If it's not relevant, you can just tell me"
3. State one micro-agenda: "I'll ask [one thing about {lead_industry} context / timing / approach], 
   and based on that I'll either share something useful or get out of your way"
4. Reference a credible reason for reaching out (e.g., "We work with companies in {lead_industry} on...")

Keep it conversational, warm. Acknowledge their time is valuable.
Ask one simple question: "Do you have {X minutes}?" or similar.

Guardrail: AADOS from Algonox. No features, pricing, or pressure. <60s total talk time before expecting reply.

Output: 2–3 sentences with 1 question. Wait for their response.''',
    2: '''You are AADOS from Algonox calling {lead_name} at {lead_company} ({lead_industry}).

Context:
- Channel: {channel}
- Tone: {tone_profile}
- Prospect: {lead_name}, {lead_title}
- Full transcript: {transcript_tail}
- Their last message: {user_input}
- Questions asked in STATE_2 so far: {state_question_count} / 2 (MAX 2 allowed)
- Current turn: {state_turn_count}

STATE_2 OBJECTIVE:
Ask your {state_question_count + 1}th discovery question. Goal: gather signal without defensiveness.

CRITICAL: Use ONLY one of these question types:
A) Multiple choice: "Is X centralized in one team, or spread across departments?"
B) Range: "Are we talking dozens or hundreds?"
C) Comparative: "Is this more/same/less of a priority than {timeframe}?"
D) External attribution: "Most teams in {lead_industry} see X — does that match?"
E) Binary simplification: "Is this a priority now, or more background?"

FORBIDDEN:
- "What's your biggest challenge?" (too open, too sales-y)
- "Why?" (defensive)
- "What's broken?" (exposure)
- Multi-part questions

Your approach:
1. Ask ONE safe discovery question from A–E above
2. Reference something they said or something typical in {lead_industry} to make it credible
3. Accept a vague answer without pushing — "Sounds like X — does that match?"
4. If {state_question_count} is already 1, this is your last question in STATE_2

Keep it conversational. Prospect should talk more than you.
Stay under 2 sentences. No features, no pressure.

Output: 1–2 sentences, 1 question. Then wait.''',
    3: '''You are AADOS from Algonox calling {lead_name} at {lead_company} ({lead_industry}).

Context:
- Channel: {channel}
- Tone: {tone_profile}
- Prospect: {lead_name}, {lead_title}
- Full transcript: {transcript_tail}
- Their last message: {user_input}
- Previous state: {previous_state_id}
- Turn in STATE_3: {state_turn_count}

STATE_3 OBJECTIVE:
Ask one deeper-but-safe discovery question. You've earned some trust; don't break it with "why" or trap questions.

ALLOWED:
- Example-based: "Is this typically triggered by X or Y?"
- Frequency: "Does this happen daily, weekly, or monthly?"
- Scope: "Does this affect the whole team or specific departments?"
- Timeline: "When did this become an issue?"
- Confirmation label: "So if I'm hearing right, it sounds like X — is that accurate?"

FORBIDDEN:
- Why questions
- "What happens if you don't fix it?"
- Long multi-part setups
- Making unverifiable claims

Approach:
1. Ask one deeper question OR ask a confirmation label based on what they said
2. Reference specifics they mentioned (not assumptions)
3. Make it quantified or example-based when possible
4. Keep prospect talking

Output: 1–2 sentences, 1 question maximum.''',
    4: '''You are AADOS from Algonox calling {lead_name} at {lead_company} ({lead_industry}).

Context:
- Prospect: {lead_name}, {lead_title}
- Full transcript: {transcript_tail}
- Their last message: {user_input}
- Channel: {channel}

STATE_4 OBJECTIVE:
Reflect back the problem you heard in one clear sentence. Prospect feels understood → you earn next question.

Required:
1. Summarize the problem in ONE sentence using their words where possible
   Example: "So it sounds like {lead_company} is juggling {X process} across multiple systems, 
   which means {Y consequence}."
2. Ask one confirmation question: "Did I get that right?" or "Is that a fair way to say it?"

DO NOT:
- Pitch a solution
- Add your own claims
- Overcomplicate the summary

Output: 1–2 sentences with 1 confirmation question. Wait for their response.''',
    5: '''You are AADOS from Algonox calling {lead_name} at {lead_company} ({lead_industry}).

Context:
- Prospect: {lead_name}, {lead_title}
- Full transcript: {transcript_tail}
- Their last message: {user_input}
- Problem we confirmed: [implicit from transcript]

STATE_5 OBJECTIVE:
Ask a light quantification question to understand scope/impact. Use ranges, not open-ended asks.

ALLOWED:
- Range: "Is this happening daily, a few times a week, or monthly?"
- Time impact: "Roughly, does a single {task} take 10 minutes or closer to an hour?"
- Scope: "Are we talking a handful of {items} or hundreds?"
- Ripple: "Does this affect just your team or multiple departments?"

FORBIDDEN:
- "What happens if you don't fix it?" (trap question)
- "How much money are you losing?"
- Open-ended "how much"
- Pressure for exact numbers

Approach:
1. Ask one range/comparative question
2. Use "roughly" or "ballpark" to soften
3. Accept proxy answers without pushing

Output: 1–2 sentences, 1 question. Accept whatever they say.''',
    6: '''You are AADOS from Algonox calling {lead_name} at {lead_company} ({lead_industry}).

Context:
- Prospect: {lead_name}, {lead_title}
- Full transcript (problem + quantification): {transcript_tail}
- Their last message: {user_input}
- Channel: {channel}

STATE_6 OBJECTIVE:
Provide one insight that reframes the problem as common + solvable. Use external attribution. Don't pitch.

Structure:
1. Start with external attribution: "What we typically see in {lead_industry}..." or "Most teams we work with..."
2. State one crisp insight tied to their problem. Keep it to 1–2 sentences.
   Example: "...is that once they centralize X, the Y problem shrinks pretty quickly."
   Example: "...is that the bottleneck isn't the process — it's ownership across the team."
3. Ask one low-pressure check: "Does that sound like what's happening?" or "Sound familiar?"

DO NOT:
- Claim results or ROI
- Mention pricing or competitors
- Over-explain
- Feature dump

Output: 2–3 sentences total with 1 check question. Then listen.''',
    7: '''You are AADOS from Algonox calling {lead_name} at {lead_company} ({lead_industry}).

Context:
- Prospect: {lead_name}, {lead_title}
- Their problem (confirmed): [from transcript]
- Full transcript: {transcript_tail}
- Their last message: {user_input}
- Channel: {channel}
- Tone: {tone_profile}

STATE_7 OBJECTIVE:
Map their problem to a high-level solution. Describe operationally, not with hype. Invite exploration.

Structure:
1. Reference their problem + the insight from STATE_6
2. Describe solution in operational terms (how teams handle it):
   Example: "What we usually do is automate the {task} step, which removes the manual work..."
   Example: "Most teams benefit from centralizing {X} in one place, so nobody's juggling multiple tools..."
   Example: "We help teams restructure so {person/team} owns the end-to-end flow instead of fragmented ownership..."
3. Ask if worth exploring: "Worth a quick 15-minute walk-through of how other teams in {lead_industry} handle this?"

DO NOT:
- Dump features
- Promise ROI or results
- Pitch aggressively
- Mention competitors

Output: 2–3 sentences, 1 exploration question. Wait for their response.''',
    8: '''You are AADOS from Algonox calling {lead_name} at {lead_company} ({lead_industry}).

Context:
- Prospect: {lead_name}, {lead_title}
- Full transcript: {transcript_tail}
- Their objection message: {user_input}
- Detected objection type: {detected_objection_type}
- Previous state: {previous_state_id}

STATE_8 OBJECTIVE:
Handle objection calmly. Use 4-step framework: Acknowledge → Clarify → Reframe → Confirm.

FRAMEWORK:
1. ACKNOWLEDGE: "I hear you — that's a fair concern."
2. CLARIFY (if needed): "Help me understand — is it specifically about [X] or the bigger picture?"
3. REFRAME using external attribution:
   - If price: "Most teams find the ROI math works once they factor in time saved, but I get wanting to understand first."
   - If timing: "That's common — teams usually start with a small pilot, not a full commitment."
   - If authority: "Smart move — we usually want [person/team] in the conversation."
   - If competition: "Makes sense to compare — what usually stands out is [integration/support/operations]."
4. CONFIRM with fair-if: "Would it make sense to [small next step], then circle back to [concern]?"

DO NOT:
- Argue or debate
- Over-talk (max 3 sentences)
- Make guarantees
- Dismiss their concern

Output: 2–3 sentences, 1 question (clarify or fair-if confirm). Then listen.''',
    9: '''You are AADOS from Algonox calling {lead_name} at {lead_company} ({lead_industry}).

Context:
- Prospect: {lead_name}, {lead_title}
- Full transcript: {transcript_tail}
- Their last message: {user_input}
- Channel: {channel}

STATE_9 OBJECTIVE:
Understand decision-making process and stakeholders lightly. Don't sound like you're qualifying them out.

APPROACH:
1. Use safe phrasing, not "Are you the decision maker?"
   - Example: "Typically there's someone from {finance/ops} involved in this — does that match your setup?"
   - Example: "When you evaluate new approaches, how does that usually work for you?"
2. Ask about PROCESS, not authority
   - Example: "Would this be a quick internal sync, or do you need more formal alignment?"
   - Example: "Does your {team/department} typically decide solo, or do you loop in {stakeholder}?"
3. Keep it one question, light and curious
4. Accept brief answers without probing further

DO NOT:
- "Are you the decision maker?"
- "Who else needs to approve?"
- Multi-part process questions
- Sound skeptical

Output: 1–2 sentences, 1 question. Then move toward next step.''',
    10: '''You are AADOS from Algonox calling {lead_name} at {lead_company} ({lead_industry}).

Context:
- Prospect: {lead_name}, {lead_title}
- Full transcript: {transcript_tail}
- Their hesitation: {user_input}
- Channel: {channel}

STATE_10 OBJECTIVE:
Lower risk of next step. Make it small, reversible, valuable even if we're not a fit.

STRUCTURE:
1. Acknowledge their hesitation (brief)
2. Offer a small, reversible next step with built-in value:
   - Example: "Let's grab 15 minutes — even if we're not a fit, you'll leave with a framework of what to look for."
   - Example: "Send me a quick note on your process, and I'll give you honest feedback on how others handle it — no pitch necessary."
   - Example: "We can schedule 30 minutes with {stakeholder} — if it's not clicking halfway through, we can stop."
3. Confirm their preference (time, method, etc.)

DO NOT:
- Make guarantees
- Use aggressive close language
- Overcomplicate the offer
- Make it sound like a sales pitch

Output: 2–3 sentences, 1 clear offer + confirmation question.''',
    11: '''You are AADOS from Algonox calling {lead_name} at {lead_company} ({lead_industry}).

Context:
- Prospect: {lead_name}, {lead_title}
- Full transcript: {transcript_tail}
- Their last message: {user_input}
- Channel: {channel}

STATE_11 OBJECTIVE:
Lock in next step as a mutual plan. Offer concrete times. Confirm what they want to see.

STRUCTURE:
1. Offer two concrete time windows (not "when are you free?"):
   - "Tuesday or Thursday work better for you?"
   - "Does next week or week after suit you?"
2. Confirm what they want to see (one detail):
   - "Just to confirm — you want to see how the automation piece works, yes?"
3. Recap the mutual action:
   - "So I'll send you a calendar link for [day/time] — we'll do a quick 30-minute walkthrough. Sound good?"
4. Keep it light: "No pressure, just exploring."

DO NOT:
- Use aggressive close language ("Let's get this booked")
- Over-sell or re-pitch
- Vague next steps
- Make it high-stakes

Output: 2–3 sentences, 1–2 confirmation questions. Recap clearly at end.''',
    12: '''You are AADOS from Algonox calling {lead_name} at {lead_company} ({lead_industry}).

Context:
- Prospect: {lead_name}, {lead_title}
- Exit reason: {detected_not_interested} | {detected_no_time} | {detected_hostile} | next_step_scheduled | discovery_complete
- Full transcript: {transcript_tail}

STATE_12 OBJECTIVE:
Exit gracefully. Preserve goodwill. Leave door open.

APPROACH BASED ON EXIT REASON:

IF next_step_scheduled:
  "Great — looking forward to [day] at [time]. I'll send the calendar link shortly. Thanks, {lead_name}."

IF not_interested or guarded:
  "No problem — I get it. Would a quick email overview be helpful, or shall I just let you go? Thanks for the time."

IF no_time:
  "Totally understand — timing is tough. Mind if I send you a quick email overview? No pressure either way."

IF hostile or tech_issues:
  "I really appreciate the time — sorry we hit a rough spot. I'll follow up via email so we can keep it clean. Thanks, {lead_name}."

ALWAYS:
1. Thank them (genuine)
2. Optionally offer email (only if not pushy)
3. Ask permission to follow up (optional, only if warm)
4. End immediately — no extended pitch

DO NOT:
- Guilt language
- Continued questions
- Desperate tone
- Pressure

Output: 1–2 sentences, 0–1 optional question. Then end the call.''',
}


class VoiceAgent:
    """
    Twilio calls our webhooks.
    We return TwiML with:
      - <Gather> to capture speech
      - Agent voice output via:
          A) OpenAI TTS MP3 -> <Play> (preferred, cedar)
          B) Twilio <Say> fallback
    """

    # ✅ IMPORTANT: persist state across VoiceAgent instances within the same process.
    _GLOBAL_CONVERSATION_STATES: Dict[int, Dict[str, Any]] = {}

    def __init__(self, db: Session):
        self.db = db
        self.twilio = TwilioService()
        self.openai = OpenAIService()

        # Fallback only
        self.twilio_say_voice = getattr(settings, "TWILIO_SAY_VOICE", None) or "alice"

        # ✅ Force OpenAI voice to cedar (male) irrespective of env
        self.openai_tts_voice_forced = "cedar"

        # Global (process) state
        self.conversation_states = VoiceAgent._GLOBAL_CONVERSATION_STATES

    # -----------------------------
    # Public base URL helpers
    # -----------------------------
    def _public_base_url(self) -> str:
        base = (getattr(settings, "TWILIO_WEBHOOK_URL", "") or "").strip()
        if not base:
            return ""
        if not base.endswith("/"):
            base += "/"
        return base

    def _should_use_openai_tts(self) -> bool:
        return bool(self._public_base_url()) and self.openai.is_tts_enabled()

    async def preheat_tts_cache(self) -> None:
        """
        Pre-generate TTS audio for common opening/closing phrases.
        Runs once at startup to warm the cache.
        """
        if not self._should_use_openai_tts():
            return

        common_phrases = [
            "Hi there — this is AADOS calling from Algonox. Did I catch you at a bad time?",
            "Before we continue—can you hear me clearly?",
            "Got it. What's the best way to think about that on your side?",
            "No problem at all—thanks for your time. I'll let you go.",
            "Totally fair—thanks for the quick response. I'll let you go.",
            "I hear you — that's a fair concern.",
            "Thanks for your time, and have a great day.",
        ]

        logger.info("[PREHEAT] Starting TTS cache pre-warming...")
        for phrase in common_phrases:
            try:
                await self.openai.tts_to_file(phrase, voice=self.openai_tts_voice_forced)
                logger.info(f"[PREHEAT] Cached: {phrase[:50]}...")
            except Exception as e:
                logger.warning(f"[PREHEAT] Failed to cache '{phrase[:30]}...': {e}")
        logger.info("[PREHEAT] TTS cache pre-warming complete")

    async def tts_audio_url(self, call_id: int, text: str) -> Optional[str]:
        """
        Generate (or reuse cached) OpenAI TTS MP3 and return a public URL for Twilio <Play>.
        If anything fails, return None => caller should fallback to Twilio <Say>.
        Timeout is 15s (aggressive for voice latency optimization).
        """
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
                voice=self.openai_tts_voice_forced,  # ✅ cedar
                timeout_s=15.0,  # Aggressive timeout for low-latency voice
            )
            tts_elapsed = (time.time() - tts_start) * 1000
            logger.info(f"[LATENCY] TTS generation for call_id={call_id}: {tts_elapsed:.2f}ms")
            filename = os.path.basename(path)
            return urljoin(self._public_base_url(), f"api/calls/{call_id}/tts/{filename}")
        except Exception as e:
            tts_elapsed = (time.time() - tts_start) * 1000
            logger.error(f"TTS generation failed (fallback to Twilio <Say>) after {tts_elapsed:.2f}ms: {e}")
            return None

    # -----------------------------
    # Conversation state
    # -----------------------------
    def _get_conversation_state(self, call_id: int) -> Dict[str, Any]:
        if call_id not in self.conversation_states:
            self.conversation_states[call_id] = {
                # Control-plane state machine
                "sales_state": SalesState.STATE_0,
                "sales_state_entered_at": datetime.utcnow(),
                "sales_state_turns": 0,
                "sales_state_questions": 0,

                # Legacy phase fields
                "phase": ConversationPhase.OPENING,
                "phase_start": datetime.utcnow(),

                # Turn counters
                "turn_count": 0,

                # Behavioral tracking
                "bant": BANTScore(),
                "pain_points": [],
                "objections": [],
                "buying_signals": [],
                "sentiment_history": [],

                # Legacy SPIN question counters (kept; not primary driver now)
                "questions_asked": {"situation": 0, "problem": 0, "implication": 0, "need_payoff": 0},

                # Call-control flags
                "end_call": False,

                # STATE_0 / STATE_1 enforcement flags
                "audio_prompted": False,
                "audio_confirmed": False,
                "tech_issue_count": 0,

                # Tone calibration
                "channel": "cold_call",
                "tone_profile": "neutral_curious",

                # Context cache
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

        # Map to legacy phase
        state["phase"] = self._map_state_to_phase(new_state)
        state["phase_start"] = datetime.utcnow()

        # End-call flag for STATE_12
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

    # -----------------------------
    # STATE_0 helpers (silent context load, tone calibrate)
    # -----------------------------
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

    # -----------------------------
    # Transcript helpers
    # -----------------------------
    def _strip_speaker_labels(self, text: str) -> str:
        if not text:
            return ""
        t = text.strip()
        t = re.sub(r"(?im)^(?:\s*(?:agent|ai agent|assistant|lead|user)\s*:\s*)+", "", t)
        t = re.sub(r"(?im)\n\s*(?:agent|ai agent|assistant|lead|user)\s*:\s*", "\n", t)
        return t.strip()

    def append_to_call_transcript(self, call: Call, speaker: str, text: str, upsert_transcripts: bool = True) -> None:
        cleaned = self._strip_speaker_labels(text)
        if not cleaned:
            return
        existing = call.full_transcript or ""
        chunk = f"{speaker.upper()}: {cleaned}"
        call.full_transcript = (existing + "\n" + chunk).strip() if existing else chunk
        self.db.commit()

    # -----------------------------
    # Opener (STATE_0 aligned: no pitching in opener)
    # -----------------------------
    def _build_opener(self, lead: Lead) -> str:
        name = (lead.name or "").strip() or "there"
        return (
            f"Hi {name} — this is AADOS calling from Algonox. "
            f"Did I catch you at a bad time?"
        )

    # -----------------------------
    # Detection helpers
    # -----------------------------
    def _detect_no_time(self, user_text: str) -> bool:
        t = (user_text or "").lower()
        return any(p in t for p in ["no time", "can't talk", "cant talk", "busy", "in a meeting", "call back later", "not now"])

    def _detect_just_tell_me(self, user_text: str) -> bool:
        t = (user_text or "").lower()
        return any(p in t for p in ["just tell me", "what do you want", "get to the point", "say it", "tell me what you want"])

    def _detect_hostile(self, user_text: str) -> bool:
        t = (user_text or "").lower()
        return any(p in t for p in ["stop calling", "don't call", "dont call", "remove me", "fuck", "f***", "leave me alone"])

    def _detect_not_interested(self, user_text: str) -> bool:
        t = (user_text or "").lower()
        return any(p in t for p in ["not interested", "no interest", "no thanks", "don't need", "dont need", "we're good", "we are good"])

    def _detect_tech_issue(self, user_text: str) -> bool:
        t = (user_text or "").lower()
        return any(p in t for p in [
            "can't hear", "cant hear", "hard to hear", "breaking up", "you are breaking up",
            "bad connection", "connection issue", "you're cutting out", "you are cutting out",
            "static", "echo", "speak up"
        ])

    def _detect_who_is_this(self, user_text: str) -> bool:
        t = (user_text or "").lower()
        return any(p in t for p in ["who is this", "who are you", "what is this about", "what's this about", "what is this"])

    def _detect_permission_granted(self, user_text: str) -> bool:
        t = (user_text or "").lower().strip()
        if not t:
            return False
        return any(p in t for p in ["sure", "okay", "ok", "go ahead", "yeah", "yes", "yep", "fine", "a minute", "quickly"])

    def _detect_permission_denied(self, user_text: str) -> bool:
        t = (user_text or "").lower()
        return any(p in t for p in ["no", "not now", "can't", "cant", "don't", "dont", "busy"]) and not self._detect_permission_granted(user_text)

    def _detect_guarded(self, user_text: str) -> bool:
        t = (user_text or "").strip()
        if not t:
            return True
        if len(t.split()) <= 2:
            return True
        return any(p in t.lower() for p in ["not sure", "hard to say", "depends", "maybe", "can't share", "cant share", "prefer not"])

    def _detect_confirm_yes(self, user_text: str) -> bool:
        t = (user_text or "").lower().strip()
        return t in ("yes", "yeah", "yep", "correct", "right", "exactly") or "that's accurate" in t or "sounds right" in t

    def _detect_resonance(self, user_text: str) -> bool:
        t = (user_text or "").lower()
        return any(p in t for p in ["makes sense", "that's true", "exactly", "right", "we see that", "agreed"])

    def _detect_hesitation(self, user_text: str) -> bool:
        t = (user_text or "").lower()
        return any(p in t for p in ["maybe", "not sure", "need to think", "send info", "email me", "circle back", "later"])

    def _detect_schedule_locked(self, user_text: str) -> bool:
        t = (user_text or "").lower()
        return any(p in t for p in ["send invite", "calendar", "book", "schedule", "tomorrow", "next week", "monday", "tuesday", "wednesday", "thursday", "friday"])

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

    # -----------------------------
    # BANT updates (kept)
    # -----------------------------
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

    # -----------------------------
    # Prompt build + postprocess
    # -----------------------------
    def _transcript_tail(self, call: Call, limit: int = 800) -> str:
        """Keep last 800 chars of transcript for context (reduced from 1800 for latency)."""
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
            company=(lead.company or "").strip() or "your company",
            industry=(getattr(lead, "company_industry", "") or "").strip() or "Unknown",
            channel=channel,
            tone_profile=tone,
            transcript_tail=self._transcript_tail(call),
            prospect_last_utterance=(user_input or "").strip(),
            state_turn_count=int(state.get("sales_state_turns", 0)),
            state_question_count=int(state.get("sales_state_questions", 0)),
            last_objection_type=last_objection_type or "none",
            last_buying_signal=last_buying_signal or "none",
            use_case_1_title=getattr(data_packet, "use_case_1_title", "") if data_packet else "",
            use_case_1_impact=getattr(data_packet, "use_case_1_impact", "") if data_packet else "",
            use_case_2_title=getattr(data_packet, "use_case_2_title", "") if data_packet else "",
            use_case_2_impact=getattr(data_packet, "use_case_2_impact", "") if data_packet else "",
            use_case_3_title=getattr(data_packet, "use_case_3_title", "") if data_packet else "",
            use_case_3_impact=getattr(data_packet, "use_case_3_impact", "") if data_packet else "",
        )
        try:
            return template.format_map(params).strip()
        except Exception:
            return template.strip()

    def _postprocess_agent_text(self, lead: Lead, text: str) -> str:
        t = self._strip_speaker_labels(text or "")
        t = re.sub(r"(?im)^AGENT\s*:\s*", "", t).strip()

        # Avoid repeated greetings / reintroductions
        name = (lead.name or "").strip()
        if name:
            t = re.sub(rf"(?im)^hi\s+{re.escape(name)}\b\s*[—,-]*\s*", "", t).strip()

        # Limit to 2 sentences max
        parts = re.split(r"(?<=[.!?])\s+", t)
        t = " ".join([p.strip() for p in parts if p.strip()][:2]).strip()

        # Ensure at most 1 question mark
        if t.count("?") > 1:
            first_q = t.find("?")
            t = t[: first_q + 1] + re.sub(r"\?", ".", t[first_q + 1 :])

        # Cap talk-time (conservative): <= 110 words
        words = t.split()
        if len(words) > 110:
            t = " ".join(words[:110]).rstrip(" ,;") + "."

        return t.strip()

    # -----------------------------
    # TwiML builders (unchanged)
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

    # -----------------------------
    # Call initiation (unchanged pipeline; state reset updated)
    # -----------------------------
    async def initiate_outbound_call(self, lead: Lead, call: Call) -> str:
        if not lead.phone and not call.phone_number:
            raise ValueError("Lead has no phone number")

        if not call.phone_number:
            call.phone_number = lead.phone

        if not call.started_at:
            call.started_at = datetime.utcnow()

        # init/reset conversation state
        state = self._get_conversation_state(call.id)
        self._set_sales_state(state, SalesState.STATE_0)
        state["end_call"] = False
        state["audio_prompted"] = False
        state["audio_confirmed"] = False
        state["tech_issue_count"] = 0
        state["turn_count"] = 0

        # STATE_0: silent context load + tone calibration
        self._silent_context_load(lead, call, state)

        opener = self._build_opener(lead)
        self.append_to_call_transcript(call, speaker="AGENT", text=opener, upsert_transcripts=False)

        self.db.commit()
        self.db.refresh(call)

        twilio_call = await self.twilio.make_call(
            to_number=call.phone_number,
            callback_url=f"/api/calls/{call.id}/webhook",
        )

        call.twilio_call_sid = getattr(twilio_call, "sid", None)
        call.status = getattr(twilio_call, "status", None) or "queued"
        self.db.commit()

        logger.info(f"Outbound call started call_id={call.id} sid={call.twilio_call_sid}")
        return call.twilio_call_sid

    # -----------------------------
    # State routing (based on user input)
    # -----------------------------
    def _route_state_before_reply(self, cur: SalesState, user_text: str, state: Dict[str, Any]) -> SalesState:
        """Given current waiting-state + prospect reply, decide what state the agent should speak in now."""

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
    # Main generation
    # -----------------------------
    async def generate_reply(self, call: Call, user_input: str) -> str:
        tracker = LatencyTracker(call_id=call.id)
        tracker.mark("reply_start")

        lead = self.db.query(Lead).filter(Lead.id == call.lead_id).first()
        packet = self.db.query(DataPacket).filter(DataPacket.lead_id == call.lead_id).first()

        if not lead:
            return "Thanks for your time."

        tracker.mark("prompt_start")
        state = self._get_conversation_state(call.id)
        self._silent_context_load(lead, call, state)

        state["turn_count"] = int(state.get("turn_count", 0)) + 1

        # ---- interrupts (highest priority) ----
        if self._detect_hostile(user_input):
            self._set_sales_state(state, SalesState.STATE_12)
            return "Understood—sorry to bother you. I’ll remove you from our list. Have a good day."

        if self._detect_tech_issue(user_input):
            state["tech_issue_count"] = int(state.get("tech_issue_count", 0)) + 1
            if state["tech_issue_count"] <= 1:
                return "Sorry—you’re breaking up a bit. Can you hear me clearly?"
            self._set_sales_state(state, SalesState.STATE_12)
            return "No worries—seems like the connection isn’t great. I’ll let you go. Have a good day."

        if self._detect_not_interested(user_input):
            self._set_sales_state(state, SalesState.STATE_12)
            return "Totally fair—thanks for the quick response. I’ll let you go."

        if any(w in (user_input or "").lower() for w in ["bye", "goodbye", "stop calling"]):
            self._set_sales_state(state, SalesState.STATE_12)
            return "Understood. Thanks for your time, and have a great day."

        cur_state: SalesState = state.get("sales_state", SalesState.STATE_0)

        # STATE_0 special-case: “who is this”
        if cur_state == SalesState.STATE_0 and self._detect_who_is_this(user_input):
            company = (lead.company or "").strip() or "your company"
            title = (lead.title or "").strip() or "your role"
            return f"This is AADOS from Algonox—I'm reaching out because you're listed as {title} at {company}. Did I catch you at a bad time?"

        # STATE_0 special-case: audio confirmation (once; before STATE_1)
        if cur_state == SalesState.STATE_0 and not state.get("audio_prompted"):
            state["audio_prompted"] = True
            return "Before we continue—can you hear me clearly?"

        if cur_state == SalesState.STATE_0 and state.get("audio_prompted") and not state.get("audio_confirmed"):
            if any(p in (user_input or "").lower() for p in ["no", "can't", "cant", "not really", "hard to hear"]):
                state["tech_issue_count"] = int(state.get("tech_issue_count", 0)) + 1
                if state["tech_issue_count"] <= 1:
                    return "Got it—let me try again. Can you hear me now?"
                self._set_sales_state(state, SalesState.STATE_12)
                return "No worries—I'll let you go and try another time. Have a good day."
            state["audio_confirmed"] = True

        if self._detect_no_time(user_input):
            self._set_sales_state(state, SalesState.STATE_12)
            email = (getattr(lead, "email", "") or "").strip()
            if email:
                return f"No worries—I’ll send a short note to {email} and let you go. Thanks for your time."
            return "No worries—I’ll send a short note and let you go. Thanks for your time."

        # Detect buying signals and objections for state templates
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

        # Route to state we should speak in NOW
        cur_state = state.get("sales_state", SalesState.STATE_0)
        speak_state = self._route_state_before_reply(cur_state, user_input, state)
        self._set_sales_state(state, speak_state)

        # If they deny permission explicitly in STATE_1, exit
        if speak_state == SalesState.STATE_1 and self._detect_permission_denied(user_input) and not self._detect_permission_granted(user_input):
            self._set_sales_state(state, SalesState.STATE_12)
            return "No problem at all—thanks for your time. I’ll let you go."

        # LLM reply for current state
        tracker.mark("prompt_end")
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

        # Check response cache before calling LLM (latency optimization)
        tracker.mark("llm_start")
        cache = get_response_cache()
        cached_reply = cache.get(int(speak_state.value), call.lead_id, user_input)

        if cached_reply:
            reply = cached_reply
            logger.info(f"[CACHE] Using cached response for state={speak_state.value} lead_id={call.lead_id}")
        else:
            reply = await self.openai.generate_completion(
                prompt=prompt,
                temperature=0.5,
                max_tokens=150,  # Reduced from 180 for faster generation (voice agents should be concise)
                timeout_s=6.0,  # Reduced from 10s for lower-latency voice interactions
            )
            # Cache the response for future calls
            if reply:
                cache.set(int(speak_state.value), call.lead_id, user_input, reply)

        tracker.mark("llm_end")
        reply_clean = self._postprocess_agent_text(lead, reply or "")
        if not reply_clean:
            # Fallback to quick acknowledgement (very fast, natural sounding)
            reply_clean = "Got it. What's the best way to think about that on your side?"

        # Update per-state counters
        state["sales_state_turns"] = int(state.get("sales_state_turns", 0)) + 1
        if "?" in reply_clean:
            state["sales_state_questions"] = int(state.get("sales_state_questions", 0)) + 1

        # Update call model fields (guard with hasattr)
        try:
            call.lead_interest_level = state["bant"].get_tier()
            call.sentiment = call.sentiment or "neutral"

            if hasattr(call, "conversation_phase"):
                call.conversation_phase = state["phase"].value
            if hasattr(call, "turn_count"):
                call.turn_count = int(state.get("turn_count", 0))
            if hasattr(call, "pain_points_count"):
                call.pain_points_count = int(len(state.get("pain_points", [])))
            if hasattr(call, "objections_count"):
                call.objections_count = int(len(state.get("objections", [])))
            if hasattr(call, "buying_signals_count"):
                call.buying_signals_count = int(len(state.get("buying_signals", [])))
            if hasattr(call, "bant_budget"):
                call.bant_budget = int(state["bant"].budget)
            if hasattr(call, "bant_authority"):
                call.bant_authority = int(state["bant"].authority)
            if hasattr(call, "bant_need"):
                call.bant_need = int(state["bant"].need)
            if hasattr(call, "bant_timeline"):
                call.bant_timeline = int(state["bant"].timeline)
            if hasattr(call, "bant_overall"):
                call.bant_overall = float(state["bant"].overall)
        except Exception:
            pass

        self.db.commit()
        tracker.log_metrics()
        return reply_clean
