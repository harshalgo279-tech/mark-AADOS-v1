# backend/app/utils/quick_responses.py
"""
Quick deterministic responses for common states that don't require LLM.
Optimizes latency by skipping API calls for predictable states.
"""

from typing import Optional
from app.utils.logger import logger


class QuickResponseHandler:
    """
    Provides fast, deterministic responses for specific states.
    Used when conversational complexity is low and LLM is unnecessary.
    """

    @staticmethod
    def should_use_quick_response(state_id: int, user_input: str) -> bool:
        """Determine if this state/input combo can use quick response."""
        # STATE_0: Initial greeting follow-up - always quick
        if state_id == 0:
            return True

        # STATE_1: Permission request - quick unless complex pushback
        if state_id == 1 and len(user_input) < 50:
            return True

        # STATE_12: Exit - always quick
        if state_id == 12:
            return True

        return False

    @staticmethod
    def get_quick_response(
        state_id: int, user_input: str, lead_name: Optional[str] = None
    ) -> Optional[str]:
        """
        Get a quick pre-written response for the state.
        Returns None if state doesn't support quick response.
        """
        user_input_lower = (user_input or "").lower().strip()

        # STATE_0 (0): Initial confirmation
        if state_id == 0:
            if any(w in user_input_lower for w in ["who", "what", "calling"]):
                return "This is AADOS from Algonox — we work with companies on operations efficiency. Did I catch you at a bad time?"
            if any(w in user_input_lower for w in ["yes", "yeah", "okay", "ok", "sure"]):
                return "Great. Before we continue — can you hear me clearly?"
            return "Got it. Can you hear me okay?"

        # STATE_1 (1): Permission/time request
        if state_id == 1:
            if any(w in user_input_lower for w in ["no time", "busy", "can't", "cant", "not now"]):
                return "No problem at all. Would a quick email overview be helpful, or shall I let you go?"
            if any(w in user_input_lower for w in ["yes", "yeah", "okay", "ok", "sure", "go"]):
                return "Perfect. I'll ask one question about your current setup, and based on that I'll either share something useful or get out of your way. Sound good?"
            if any(w in user_input_lower for w in ["minute", "few", "quick", "short"]):
                return "Perfect. Quick question: is this something you handle in your role, or do you work with someone else on this?"
            return "Thanks for your time. Do you have a few minutes?"

        # STATE_12 (12): Exit/goodbye
        if state_id == 12:
            if any(w in user_input_lower for w in ["thanks", "thank you", "bye", "goodbye"]):
                return "Take care, and have a great day."
            if any(w in user_input_lower for w in ["no", "not interested", "remove me"]):
                return "Totally understand. I'll remove you from our list. Have a great day."
            if any(w in user_input_lower for w in ["email", "send info"]):
                return "I'll send you something via email. Thanks for the time."
            return "Thanks for your time, and have a great day."

        return None

    @staticmethod
    def log_quick_response_usage(
        state_id: int, user_input: str, response: str
    ) -> None:
        """Log when quick response is used."""
        logger.info(
            f"[QUICK_RESPONSE] state={state_id} | input_len={len(user_input)} | "
            f"response_len={len(response)} | Skipped LLM call (latency saving: ~1.5-2s)"
        )


def try_quick_response(
    state_id: int, user_input: str, lead_name: Optional[str] = None
) -> Optional[str]:
    """
    Attempt to get a quick response. Returns None if LLM is needed.
    """
    handler = QuickResponseHandler()

    if not handler.should_use_quick_response(state_id, user_input):
        return None

    response = handler.get_quick_response(state_id, user_input, lead_name)

    if response:
        handler.log_quick_response_usage(state_id, user_input, response)

    return response
