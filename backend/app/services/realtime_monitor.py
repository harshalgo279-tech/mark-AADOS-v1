# backend/app/services/realtime_monitor.py
"""
Real-time conversation monitoring service for ElevenLabs.
Uses REST API polling to fetch transcript updates and forward to frontend.
(WebSocket monitoring requires enterprise subscription)

Enhanced with:
- Conversation tracking to prevent repetitive questions
- Failure mode detection
- State tracking
- Call watchdog timer for automatic termination
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional, Callable, Awaitable

import httpx

from app.config import settings
from app.utils.logger import logger
from app.agents.sales_control_plane import (
    get_or_create_tracker,
    clear_tracker,
    ConversationTracker,
    FailureMode,
)


class RealtimeMonitor:
    """
    Monitors ElevenLabs conversations in real-time via REST API polling.
    Streams transcript events to a callback function (typically your frontend WebSocket broadcast).

    Includes a watchdog timer that will emit a warning event if the call exceeds
    the maximum duration configured in settings.
    """

    POLL_INTERVAL = 2.0  # seconds between polls
    MAX_POLL_DURATION = 900  # 15 minutes max polling
    WATCHDOG_CHECK_INTERVAL = 30  # Check watchdog every 30 seconds

    def __init__(
        self,
        conversation_id: str,
        call_id: int,
        lead_id: int,
        on_transcript: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        twilio_call_sid: Optional[str] = None,
    ):
        self.conversation_id = conversation_id
        self.call_id = call_id
        self.lead_id = lead_id
        self.on_transcript = on_transcript
        self.twilio_call_sid = twilio_call_sid

        self.api_key = (getattr(settings, "ELEVENLABS_API_KEY", "") or "").strip()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._watchdog_task: Optional[asyncio.Task] = None
        self._last_transcript_count = 0  # Track how many transcript entries we've seen
        self._full_transcript_data: list = []  # Store full transcript for DB save
        self._start_time: Optional[float] = None
        self._watchdog_triggered = False

        # Get max call duration from config (default 10 minutes)
        self._max_call_duration = getattr(settings, "MAX_CALL_DURATION_SECONDS", 600)

        # Initialize conversation tracker for this conversation
        self.tracker = get_or_create_tracker(conversation_id)

    @property
    def conversation_url(self) -> str:
        return f"https://api.elevenlabs.io/v1/convai/conversations/{self.conversation_id}"

    async def _safe_callback(self, data: Dict[str, Any]) -> None:
        """
        Safely invoke the on_transcript callback with exception handling.
        Prevents callback exceptions from crashing the poll loop.
        """
        if not self.on_transcript:
            return
        try:
            await self.on_transcript(data)
        except Exception as e:
            logger.error(
                f"Callback exception for call_id={self.call_id}, type={data.get('type', 'unknown')}: {e}"
            )

    async def start(self) -> None:
        """Start monitoring the conversation with watchdog timer."""
        if not self.api_key:
            logger.error("ELEVENLABS_API_KEY missing. Cannot monitor conversation.")
            return

        if self._running:
            return

        self._running = True
        self._start_time = time.time()
        self._task = asyncio.create_task(self._poll_loop())
        self._watchdog_task = asyncio.create_task(self._watchdog_loop())
        logger.info(
            f"Started real-time monitor (polling) for conversation_id={self.conversation_id}, "
            f"call_id={self.call_id}, max_duration={self._max_call_duration}s"
        )

    async def stop(self) -> None:
        """Stop monitoring the conversation and clean up tracker."""
        self._running = False

        # Cancel watchdog task
        if self._watchdog_task:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass

        # Cancel main polling task
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        # Clean up conversation tracker
        clear_tracker(self.conversation_id)
        logger.info(f"Stopped real-time monitor for conversation_id={self.conversation_id}")

    async def _watchdog_loop(self) -> None:
        """
        Watchdog timer that monitors call duration.
        Emits a warning event and optionally terminates the call if it exceeds max duration.
        """
        warning_threshold = self._max_call_duration * 0.9  # Warn at 90% of max
        warning_sent = False

        while self._running:
            try:
                await asyncio.sleep(self.WATCHDOG_CHECK_INTERVAL)

                if not self._running or self._start_time is None:
                    break

                elapsed = time.time() - self._start_time

                # Send warning at 90% of max duration
                if not warning_sent and elapsed >= warning_threshold:
                    warning_sent = True
                    remaining = int(self._max_call_duration - elapsed)
                    logger.warning(
                        f"[WATCHDOG] Call {self.call_id} approaching max duration. "
                        f"Elapsed: {int(elapsed)}s, Remaining: {remaining}s"
                    )
                    await self._safe_callback({
                        "type": "watchdog_warning",
                        "call_id": self.call_id,
                        "lead_id": self.lead_id,
                        "elapsed_seconds": int(elapsed),
                        "remaining_seconds": remaining,
                        "message": f"Call approaching max duration ({remaining}s remaining)",
                    })

                # Trigger watchdog if call exceeds max duration
                if elapsed >= self._max_call_duration and not self._watchdog_triggered:
                    self._watchdog_triggered = True
                    logger.error(
                        f"[WATCHDOG] Call {self.call_id} exceeded max duration of {self._max_call_duration}s. "
                        f"Elapsed: {int(elapsed)}s"
                    )

                    await self._safe_callback({
                        "type": "watchdog_timeout",
                        "call_id": self.call_id,
                        "lead_id": self.lead_id,
                        "elapsed_seconds": int(elapsed),
                        "max_duration": self._max_call_duration,
                        "message": "Call exceeded maximum duration - watchdog triggered",
                    })

                    # Attempt to end the call via Twilio if we have the call SID
                    if self.twilio_call_sid:
                        await self._terminate_call_via_twilio()

                    break

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[WATCHDOG] Error in watchdog loop for call_id={self.call_id}: {e}")

    async def _terminate_call_via_twilio(self) -> None:
        """Attempt to terminate the call via Twilio API."""
        try:
            from app.services.twilio_service import TwilioService

            twilio = TwilioService()
            success = await twilio.end_call(self.twilio_call_sid)
            if success:
                logger.info(f"[WATCHDOG] Successfully terminated call {self.twilio_call_sid}")
            else:
                logger.warning(f"[WATCHDOG] Failed to terminate call {self.twilio_call_sid}")
        except Exception as e:
            logger.error(f"[WATCHDOG] Error terminating call {self.twilio_call_sid}: {e}")

    async def _poll_loop(self) -> None:
        """Main polling loop - fetches conversation data and extracts new transcript entries."""
        poll_count = 0
        max_polls = int(self.MAX_POLL_DURATION / self.POLL_INTERVAL)
        consecutive_errors = 0

        # Notify frontend that monitoring started
        await self._safe_callback({
            "type": "realtime_monitor_connected",
            "call_id": self.call_id,
            "lead_id": self.lead_id,
            "conversation_id": self.conversation_id,
            "message": "Real-time transcript streaming started (polling mode)",
        })

        async with httpx.AsyncClient(timeout=10.0) as client:
            while self._running and poll_count < max_polls:
                try:
                    response = await client.get(
                        self.conversation_url,
                        headers={"xi-api-key": self.api_key}
                    )

                    if response.status_code == 200:
                        data = response.json()
                        consecutive_errors = 0

                        # Process new transcript entries
                        await self._process_transcript(data)

                        # Check if conversation ended
                        status = data.get("status", "")
                        if status == "done":
                            logger.info(f"Conversation ended for call_id={self.call_id}")

                            # Final fetch to ensure we get all transcript entries
                            await asyncio.sleep(1.0)
                            try:
                                final_response = await client.get(
                                    self.conversation_url,
                                    headers={"xi-api-key": self.api_key}
                                )
                                if final_response.status_code == 200:
                                    final_data = final_response.json()
                                    await self._process_transcript(final_data)

                                    # Save transcript to database
                                    await self._save_transcript_to_db(final_data)
                            except Exception as e:
                                logger.warning(f"Final transcript fetch failed: {e}")

                            await self._safe_callback({
                                "type": "realtime_call_ended",
                                "call_id": self.call_id,
                                "lead_id": self.lead_id,
                                "message": "Call ended",
                            })
                            break

                    elif response.status_code == 404:
                        # Conversation not found yet, might still be initializing
                        logger.debug(f"Conversation {self.conversation_id} not found yet")
                        consecutive_errors += 1

                    else:
                        logger.warning(f"Poll error {response.status_code}: {response.text[:200]}")
                        consecutive_errors += 1

                except httpx.TimeoutException:
                    logger.warning(f"Poll timeout for call_id={self.call_id}")
                    consecutive_errors += 1
                except Exception as e:
                    logger.error(f"Poll error for call_id={self.call_id}: {e}")
                    consecutive_errors += 1

                # Stop if too many consecutive errors
                if consecutive_errors >= 10:
                    logger.error(f"Too many consecutive errors, stopping monitor for call_id={self.call_id}")
                    break

                poll_count += 1
                await asyncio.sleep(self.POLL_INTERVAL)

        # Notify frontend that monitoring ended
        await self._safe_callback({
            "type": "realtime_monitor_disconnected",
            "call_id": self.call_id,
            "lead_id": self.lead_id,
            "message": "Real-time transcript streaming ended",
        })

        self._running = False

    async def _process_transcript(self, data: Dict[str, Any]) -> None:
        """Process transcript data, track conversation context, and emit new entries."""
        transcript = data.get("transcript", [])

        if not transcript:
            return

        # Store full transcript for later DB save
        self._full_transcript_data = transcript

        # Only process new entries
        new_entries = transcript[self._last_transcript_count:]

        if new_entries:
            logger.info(f"Found {len(new_entries)} new transcript entries for call_id={self.call_id}")

        for entry in new_entries:
            role = entry.get("role", "").lower()
            message = entry.get("message", "")

            if not message:
                continue

            # Map roles: agent -> AGENT, user -> LEAD
            mapped_role = "AGENT" if role == "agent" else "LEAD"

            # ========== CONVERSATION TRACKING ==========
            self.tracker.turn_count += 1

            if mapped_role == "AGENT":
                # Track agent questions to prevent repetition
                if "?" in message:
                    # Check if this is a repeated question
                    is_duplicate, original = self.tracker.is_question_already_asked(message)
                    if is_duplicate:
                        logger.warning(
                            f"[REPETITION DETECTED] call_id={self.call_id}: Agent asked similar question again. "
                            f"Original: '{original.question_text[:50]}...' New: '{message[:50]}...'"
                        )
                    self.tracker.record_question(message)

                # Extract topics from agent speech
                self._extract_and_track_topics(message, "agent")

            else:  # LEAD response
                # Analyze for failure modes
                failure_mode = self.tracker.detect_failure_mode(message)
                if failure_mode:
                    self.tracker.detected_failure_modes.append(
                        (failure_mode, __import__('datetime').datetime.utcnow(), message)
                    )
                    logger.info(f"[FAILURE MODE DETECTED] call_id={self.call_id}: {failure_mode.value}")

                    # Emit failure mode event to frontend
                    await self._safe_callback({
                        "type": "failure_mode_detected",
                        "call_id": self.call_id,
                        "lead_id": self.lead_id,
                        "failure_mode": failure_mode.value,
                        "suggested_response": self.tracker.get_failure_mode_response(failure_mode),
                    })

                # Update engagement score based on response length and sentiment
                self._update_engagement_score(message)

                # Extract information from prospect responses
                self._extract_gathered_info(message)

                # Update last question's answer status
                if self.tracker.asked_questions:
                    last_q = self.tracker.asked_questions[-1]
                    if not last_q.got_answer:
                        last_q.got_answer = True
                        last_q.answer_summary = message[:100]

            # ========== END CONVERSATION TRACKING ==========

            logger.info(f"Realtime transcript [{mapped_role}] call_id={self.call_id}: {message[:80]}...")

            await self._safe_callback({
                "type": "realtime_transcript",
                "call_id": self.call_id,
                "lead_id": self.lead_id,
                "role": mapped_role,
                "text": message,
                "is_final": True,
                "time_in_call_secs": entry.get("time_in_call_secs", 0),
                # Include tracking context
                "conversation_state": self.tracker.current_state.value,
                "turn_count": self.tracker.turn_count,
                "engagement_score": self.tracker.prospect_engagement_score,
            })

        self._last_transcript_count = len(transcript)

    def _extract_and_track_topics(self, message: str, speaker: str) -> None:
        """Extract topics mentioned in the message and track them."""
        # Common business topics to track
        topic_keywords = {
            "automation": ["automat", "workflow", "process"],
            "cost": ["cost", "budget", "spend", "price", "expensive"],
            "time": ["time", "hours", "days", "weeks"],
            "team": ["team", "staff", "employee", "people"],
            "software": ["software", "tool", "system", "platform"],
            "data": ["data", "analytics", "report", "metric"],
            "integration": ["integrat", "connect", "sync"],
            "security": ["security", "compliance", "privacy"],
            "scale": ["scale", "grow", "expand"],
        }

        message_lower = message.lower()
        for topic, keywords in topic_keywords.items():
            if any(kw in message_lower for kw in keywords):
                self.tracker.record_topic(topic, speaker)

    def _update_engagement_score(self, response: str) -> None:
        """Update prospect engagement score based on response characteristics."""
        words = len(response.split())

        # Short responses indicate lower engagement
        if words < 5:
            self.tracker.prospect_engagement_score = max(1, self.tracker.prospect_engagement_score - 1)
            self.tracker.energy_level = "low"
        elif words > 20:
            self.tracker.prospect_engagement_score = min(10, self.tracker.prospect_engagement_score + 1)
            self.tracker.energy_level = "high"
        else:
            self.tracker.energy_level = "medium"

        # Positive signals
        positive_signals = ["interesting", "tell me more", "how does", "that sounds", "yes", "definitely"]
        if any(signal in response.lower() for signal in positive_signals):
            self.tracker.prospect_engagement_score = min(10, self.tracker.prospect_engagement_score + 1)

        # Negative signals
        negative_signals = ["not sure", "i don't know", "maybe later", "no thanks", "not interested"]
        if any(signal in response.lower() for signal in negative_signals):
            self.tracker.prospect_engagement_score = max(1, self.tracker.prospect_engagement_score - 1)

    def _extract_gathered_info(self, response: str) -> None:
        """Extract and categorize information from prospect responses."""
        response_lower = response.lower()

        # Pain points
        pain_indicators = ["struggle", "difficult", "challenge", "problem", "issue", "frustrated", "annoying"]
        if any(indicator in response_lower for indicator in pain_indicators):
            self.tracker.record_gathered_info("pain_points", response[:100])

        # Budget signals
        budget_indicators = ["budget", "cost", "afford", "expensive", "cheap", "price"]
        if any(indicator in response_lower for indicator in budget_indicators):
            self.tracker.record_gathered_info("budget_signals", response[:100])

        # Timeline signals
        timeline_indicators = ["soon", "urgent", "asap", "next quarter", "this year", "deadline"]
        if any(indicator in response_lower for indicator in timeline_indicators):
            self.tracker.record_gathered_info("timeline_signals", response[:100])

        # Authority info
        authority_indicators = ["boss", "manager", "ceo", "director", "team", "committee", "board"]
        if any(indicator in response_lower for indicator in authority_indicators):
            self.tracker.record_gathered_info("authority_info", response[:100])

        # Objections
        objection_indicators = ["but", "however", "concern", "worry", "not sure", "might not"]
        if any(indicator in response_lower for indicator in objection_indicators):
            self.tracker.record_gathered_info("objections", response[:100])

    async def _save_transcript_to_db(self, data: Dict[str, Any]) -> None:
        """Save the transcript to the database when the call ends."""
        try:
            # Import here to avoid circular imports
            from app.database import SessionLocal
            from app.models.call import Call
            from app.pipelines.call_pipeline import run_post_call_pipeline
            from app.api.websocket import broadcast_activity

            transcript = data.get("transcript", [])
            if not transcript:
                logger.warning(f"No transcript to save for call_id={self.call_id}")
                return

            # Format transcript like the post-call webhook does
            lines = []
            for entry in transcript:
                role = entry.get("role", "").lower()
                message = (entry.get("message") or "").strip()
                if not message:
                    continue
                # Map roles: agent -> AGENT, user -> LEAD
                label = "AGENT" if role == "agent" else "LEAD"
                lines.append(f"{label}: {message}")

            full_transcript = "\n".join(lines).strip()
            if not full_transcript:
                logger.warning(f"Empty transcript for call_id={self.call_id}")
                return

            # Get duration from metadata
            metadata = data.get("metadata", {})
            duration = metadata.get("call_duration_secs")

            # If duration not available, calculate from last transcript entry
            if not duration and transcript:
                last_entry = transcript[-1]
                duration = last_entry.get("time_in_call_secs", 0)

            # Save to database
            db = SessionLocal()
            try:
                call = db.query(Call).filter(Call.id == self.call_id).first()
                if not call:
                    logger.error(f"Call not found for call_id={self.call_id}")
                    return

                call.full_transcript = full_transcript
                call.status = "completed"
                if duration:
                    call.duration = int(duration)
                call.elevenlabs_conversation_id = self.conversation_id

                db.commit()
                logger.info(f"Saved transcript to database for call_id={self.call_id} ({len(lines)} turns, {duration}s)")

                # Broadcast that transcript is ready
                await broadcast_activity({
                    "type": "call_transcript_ready",
                    "call_id": self.call_id,
                    "lead_id": self.lead_id,
                    "message": f"Transcript ready ({len(lines)} turns)",
                })

                # Run post-call pipeline (analysis, follow-up email, etc.)
                asyncio.create_task(run_post_call_pipeline(self.call_id))

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Failed to save transcript to DB for call_id={self.call_id}: {e}")


# =============================================================================
# GLOBAL MONITOR REGISTRY - Thread-Safe with Memory Management
# =============================================================================

import threading

# Global registry of active monitors with thread safety
_active_monitors: Dict[int, RealtimeMonitor] = {}
_monitors_lock = asyncio.Lock()
_monitors_sync_lock = threading.Lock()  # For synchronous access

# Memory limits
MAX_ACTIVE_MONITORS = 100  # Maximum concurrent monitors


async def start_realtime_monitor(
    conversation_id: str,
    call_id: int,
    lead_id: int,
    on_transcript: Callable[[Dict[str, Any]], Awaitable[None]],
) -> None:
    """Start monitoring a conversation and add to registry (thread-safe)."""
    async with _monitors_lock:
        # Stop existing monitor if any
        if call_id in _active_monitors:
            old_monitor = _active_monitors.pop(call_id)
            try:
                await old_monitor.stop()
            except Exception as e:
                logger.warning(f"Error stopping old monitor for call_id={call_id}: {e}")

        # Enforce memory limit
        if len(_active_monitors) >= MAX_ACTIVE_MONITORS:
            # Remove oldest monitors (by call_id as proxy for age)
            oldest_ids = sorted(_active_monitors.keys())[:10]
            for old_id in oldest_ids:
                old_mon = _active_monitors.pop(old_id, None)
                if old_mon:
                    try:
                        await old_mon.stop()
                    except Exception:
                        pass
                    logger.warning(f"Evicted monitor for call_id={old_id} due to memory limit")

        monitor = RealtimeMonitor(
            conversation_id=conversation_id,
            call_id=call_id,
            lead_id=lead_id,
            on_transcript=on_transcript,
        )
        _active_monitors[call_id] = monitor

    # Start outside the lock to avoid holding it during I/O
    await monitor.start()


async def stop_realtime_monitor(call_id: int) -> None:
    """Stop monitoring a conversation and remove from registry (thread-safe)."""
    monitor = None
    async with _monitors_lock:
        monitor = _active_monitors.pop(call_id, None)

    if monitor:
        try:
            await monitor.stop()
        except Exception as e:
            logger.error(f"Error stopping monitor for call_id={call_id}: {e}")


def get_active_monitor(call_id: int) -> Optional[RealtimeMonitor]:
    """Get active monitor for a call (thread-safe sync access)."""
    with _monitors_sync_lock:
        return _active_monitors.get(call_id)


def get_active_monitor_count() -> int:
    """Get count of active monitors (for monitoring)."""
    with _monitors_sync_lock:
        return len(_active_monitors)


async def cleanup_all_monitors() -> int:
    """
    Stop and remove all monitors. Call on shutdown.
    Returns number of monitors stopped.
    """
    async with _monitors_lock:
        monitors = list(_active_monitors.values())
        _active_monitors.clear()

    count = 0
    for monitor in monitors:
        try:
            await monitor.stop()
            count += 1
        except Exception as e:
            logger.error(f"Error stopping monitor during cleanup: {e}")

    return count
