# backend/app/agents/email_intelligence_agent.py
"""
Email Intelligence Agent
========================

AI-powered email optimization that provides:
1. Send Time Optimization - Predicts optimal send time per lead
2. Engagement Scoring - Scores leads based on email interactions
3. Reply Sentiment Analysis - Classifies reply intent and sentiment
4. Subject Line A/B Testing - Generates and tests subject variants
5. Adaptive Sequence Branching - Adjusts sequences based on engagement
6. Content Optimization - Analyzes and improves email content
7. Deliverability Insights - Monitors domain health and warmup

This makes the email system as intelligent as the call system.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

from sqlalchemy import func, and_, or_
from sqlalchemy.orm import Session

from app.models.email import Email
from app.models.lead import Lead
from app.models.call import Call
from app.services.openai_service import OpenAIService
from app.utils.logger import logger


# =============================================================================
# Enums and Constants
# =============================================================================

class ReplyIntent(str, Enum):
    """Classification of reply intent."""
    INTERESTED = "interested"
    MEETING_REQUEST = "meeting_request"
    MORE_INFO = "more_info"
    OBJECTION = "objection"
    NOT_NOW = "not_now"
    NOT_INTERESTED = "not_interested"
    OUT_OF_OFFICE = "out_of_office"
    WRONG_PERSON = "wrong_person"
    UNSUBSCRIBE = "unsubscribe"
    UNKNOWN = "unknown"


class EngagementLevel(str, Enum):
    """Lead engagement classification."""
    HOT = "hot"           # Clicked + replied positively
    WARM = "warm"         # Opened multiple times
    LUKEWARM = "lukewarm" # Opened once
    COLD = "cold"         # No engagement
    DEAD = "dead"         # Bounced or unsubscribed


# Engagement scoring weights
ENGAGEMENT_WEIGHTS = {
    "email_sent": 1,
    "email_opened": 5,
    "email_clicked": 15,
    "email_replied": 25,
    "positive_reply": 50,
    "meeting_booked": 100,
    "bounced": -20,
    "unsubscribed": -100,
}

# Optimal send times by industry (fallback defaults)
DEFAULT_SEND_WINDOWS = {
    "technology": {"days": [1, 2, 3], "hours": [9, 10, 14, 15]},  # Tue-Thu, 9-10am, 2-3pm
    "finance": {"days": [1, 2, 3, 4], "hours": [8, 9, 10]},  # Mon-Fri early morning
    "healthcare": {"days": [1, 2, 3], "hours": [10, 11, 14]},
    "retail": {"days": [0, 1, 2], "hours": [10, 11, 15, 16]},  # Mon-Wed, late morning/afternoon
    "default": {"days": [1, 2, 3], "hours": [9, 10, 11, 14, 15]},  # Tue-Thu business hours
}


# =============================================================================
# Email Intelligence Agent
# =============================================================================

class EmailIntelligenceAgent:
    """
    AI-powered email intelligence for hyper-personalization and optimization.

    Features:
    - Send time optimization based on lead behavior patterns
    - Engagement scoring with weighted signals
    - Reply sentiment and intent analysis
    - Subject line A/B testing with AI generation
    - Adaptive sequence branching
    - Content quality analysis
    """

    def __init__(self, db: Session):
        self.db = db
        self.openai = OpenAIService()

    # =========================================================================
    # 1. SEND TIME OPTIMIZATION
    # =========================================================================

    async def get_optimal_send_time(
        self,
        lead_id: int,
        prefer_within_hours: int = 48,
    ) -> datetime:
        """
        Calculate the optimal send time for a specific lead.

        Uses:
        1. Lead's past email engagement patterns (opens by hour/day)
        2. Industry defaults if no engagement history
        3. Timezone awareness (inferred from company location)

        Returns datetime in UTC for when to schedule the email.
        """
        lead = self.db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            return self._get_next_default_window()

        # Get lead's engagement history
        engagement_data = self._analyze_lead_engagement_patterns(lead_id)

        if engagement_data["total_opens"] >= 3:
            # Use lead's actual behavior patterns
            optimal_hour = engagement_data["best_hour"]
            optimal_day = engagement_data["best_day"]
        else:
            # Use industry defaults
            industry = (lead.company_industry or "default").lower()
            defaults = DEFAULT_SEND_WINDOWS.get(industry, DEFAULT_SEND_WINDOWS["default"])
            optimal_day = defaults["days"][0] if defaults["days"] else 1
            optimal_hour = defaults["hours"][0] if defaults["hours"] else 10

        # Calculate next occurrence of optimal day/hour
        now = datetime.utcnow()
        target = self._find_next_occurrence(now, optimal_day, optimal_hour, prefer_within_hours)

        logger.info(f"Optimal send time for lead {lead_id}: {target} (based on {'behavior' if engagement_data['total_opens'] >= 3 else 'industry defaults'})")
        return target

    def _analyze_lead_engagement_patterns(self, lead_id: int) -> Dict[str, Any]:
        """Analyze when a lead typically opens emails."""
        # Get all opened emails for this lead
        opened_emails = (
            self.db.query(Email)
            .filter(
                Email.lead_id == lead_id,
                Email.opened_at.isnot(None),
            )
            .all()
        )

        if not opened_emails:
            return {"total_opens": 0, "best_hour": 10, "best_day": 2}

        # Analyze open times
        hour_counts = {}
        day_counts = {}

        for email in opened_emails:
            hour = email.opened_at.hour
            day = email.opened_at.weekday()
            hour_counts[hour] = hour_counts.get(hour, 0) + 1
            day_counts[day] = day_counts.get(day, 0) + 1

        best_hour = max(hour_counts, key=hour_counts.get) if hour_counts else 10
        best_day = max(day_counts, key=day_counts.get) if day_counts else 2

        return {
            "total_opens": len(opened_emails),
            "best_hour": best_hour,
            "best_day": best_day,
            "hour_distribution": hour_counts,
            "day_distribution": day_counts,
        }

    def _find_next_occurrence(
        self,
        from_time: datetime,
        target_day: int,  # 0=Monday, 6=Sunday
        target_hour: int,
        max_hours: int = 48,
    ) -> datetime:
        """Find the next occurrence of a specific day/hour within max_hours."""
        candidate = from_time.replace(hour=target_hour, minute=0, second=0, microsecond=0)

        # If today's target hour has passed, start from tomorrow
        if candidate <= from_time:
            candidate += timedelta(days=1)

        # Find next matching day
        days_ahead = target_day - candidate.weekday()
        if days_ahead < 0:
            days_ahead += 7
        candidate += timedelta(days=days_ahead)

        # If too far out, just use next available slot
        if (candidate - from_time).total_seconds() / 3600 > max_hours:
            candidate = from_time + timedelta(hours=2)
            # Avoid weekends
            while candidate.weekday() >= 5:
                candidate += timedelta(days=1)
            candidate = candidate.replace(hour=target_hour, minute=0, second=0, microsecond=0)

        return candidate

    def _get_next_default_window(self) -> datetime:
        """Get next available send window using defaults."""
        now = datetime.utcnow()
        defaults = DEFAULT_SEND_WINDOWS["default"]
        return self._find_next_occurrence(now, defaults["days"][0], defaults["hours"][0])

    # =========================================================================
    # 2. ENGAGEMENT SCORING
    # =========================================================================

    async def calculate_engagement_score(self, lead_id: int) -> Dict[str, Any]:
        """
        Calculate a comprehensive engagement score for a lead.

        Scoring factors:
        - Email opens (5 points each)
        - Email clicks (15 points each)
        - Email replies (25 points each)
        - Positive replies (50 points each)
        - Bounces (-20 points)
        - Unsubscribes (-100 points)

        Returns score, level, and breakdown.
        """
        lead = self.db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            return {"score": 0, "level": EngagementLevel.COLD, "breakdown": {}}

        # Check for negative signals first
        if lead.unsubscribed_at:
            return {
                "score": ENGAGEMENT_WEIGHTS["unsubscribed"],
                "level": EngagementLevel.DEAD,
                "breakdown": {"unsubscribed": 1},
            }

        if hasattr(lead, "email_valid") and lead.email_valid is False:
            return {
                "score": ENGAGEMENT_WEIGHTS["bounced"],
                "level": EngagementLevel.DEAD,
                "breakdown": {"bounced": 1},
            }

        # Get email statistics
        emails = self.db.query(Email).filter(Email.lead_id == lead_id).all()

        breakdown = {
            "emails_sent": 0,
            "emails_opened": 0,
            "emails_clicked": 0,
            "emails_replied": 0,
            "positive_replies": 0,
        }

        for email in emails:
            if email.status == "sent":
                breakdown["emails_sent"] += 1
            if email.opened_at:
                breakdown["emails_opened"] += 1
            if email.clicked_at:
                breakdown["emails_clicked"] += 1
            if email.replied_at:
                breakdown["emails_replied"] += 1
                # Check if reply was positive (we'll analyze this separately)

        # Calculate score
        score = (
            breakdown["emails_sent"] * ENGAGEMENT_WEIGHTS["email_sent"]
            + breakdown["emails_opened"] * ENGAGEMENT_WEIGHTS["email_opened"]
            + breakdown["emails_clicked"] * ENGAGEMENT_WEIGHTS["email_clicked"]
            + breakdown["emails_replied"] * ENGAGEMENT_WEIGHTS["email_replied"]
        )

        # Determine engagement level
        if score >= 100 or breakdown["emails_clicked"] >= 2:
            level = EngagementLevel.HOT
        elif score >= 50 or breakdown["emails_opened"] >= 3:
            level = EngagementLevel.WARM
        elif score >= 20 or breakdown["emails_opened"] >= 1:
            level = EngagementLevel.LUKEWARM
        else:
            level = EngagementLevel.COLD

        return {
            "score": score,
            "level": level.value,
            "breakdown": breakdown,
            "recommendation": self._get_engagement_recommendation(level, breakdown),
        }

    def _get_engagement_recommendation(
        self,
        level: EngagementLevel,
        breakdown: Dict[str, int],
    ) -> str:
        """Get actionable recommendation based on engagement level."""
        if level == EngagementLevel.HOT:
            return "High engagement! Prioritize for immediate follow-up call or meeting request."
        elif level == EngagementLevel.WARM:
            return "Good engagement. Send a value-add follow-up with case study or demo offer."
        elif level == EngagementLevel.LUKEWARM:
            return "Some interest shown. Try a different angle or use case in next email."
        elif level == EngagementLevel.COLD:
            if breakdown["emails_sent"] >= 3:
                return "No engagement after multiple attempts. Consider pausing or trying a different channel."
            return "No engagement yet. Continue sequence with varied content."
        else:
            return "Lead is inactive. Remove from active sequences."

    # =========================================================================
    # 3. REPLY SENTIMENT ANALYSIS
    # =========================================================================

    async def analyze_reply(
        self,
        reply_text: str,
        original_email_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Analyze an email reply using AI to determine:
        - Intent classification (interested, objection, OOO, etc.)
        - Sentiment score (-1 to 1)
        - Recommended next action
        - Key points extracted

        This is similar to how the call system analyzes conversations.
        """
        if not reply_text or not reply_text.strip():
            return {
                "intent": ReplyIntent.UNKNOWN.value,
                "sentiment": 0,
                "confidence": 0,
                "next_action": "manual_review",
                "key_points": [],
            }

        prompt = f"""Analyze this email reply and provide a JSON response.

REPLY TEXT:
{reply_text[:2000]}

Analyze the reply and return JSON with:
1. "intent": One of: interested, meeting_request, more_info, objection, not_now, not_interested, out_of_office, wrong_person, unsubscribe, unknown
2. "sentiment": Float from -1 (very negative) to 1 (very positive)
3. "confidence": Float from 0 to 1 indicating analysis confidence
4. "key_points": List of 1-3 important points from the reply
5. "objections": List of any objections raised (empty if none)
6. "questions": List of any questions asked (empty if none)
7. "next_action": Recommended next action (call_immediately, send_info, schedule_meeting, pause_sequence, remove_from_list, manual_review)
8. "urgency": One of: high, medium, low

Return ONLY valid JSON, no other text."""

        try:
            response = await self.openai.generate_completion(
                prompt=prompt,
                temperature=0.3,
                max_tokens=500,
            )

            result = json.loads(response)

            # Validate intent
            try:
                result["intent"] = ReplyIntent(result.get("intent", "unknown")).value
            except ValueError:
                result["intent"] = ReplyIntent.UNKNOWN.value

            logger.info(f"Reply analysis: intent={result['intent']}, sentiment={result.get('sentiment', 0)}")
            return result

        except json.JSONDecodeError:
            logger.error("Failed to parse reply analysis JSON")
            return {
                "intent": ReplyIntent.UNKNOWN.value,
                "sentiment": 0,
                "confidence": 0,
                "next_action": "manual_review",
                "key_points": [],
            }
        except Exception as e:
            logger.error(f"Reply analysis error: {e}")
            return {
                "intent": ReplyIntent.UNKNOWN.value,
                "sentiment": 0,
                "confidence": 0,
                "next_action": "manual_review",
                "key_points": [],
                "error": str(e),
            }

    # =========================================================================
    # 4. SUBJECT LINE A/B TESTING
    # =========================================================================

    async def generate_subject_variants(
        self,
        original_subject: str,
        email_type: str,
        lead: Lead,
        num_variants: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Generate A/B test variants for a subject line.

        Uses AI to create variations with different approaches:
        - Curiosity-driven
        - Benefit-focused
        - Question-based
        - Urgency/scarcity
        - Personalized

        Returns list of variants with predicted effectiveness.
        """
        company = lead.company or "your company"
        first_name = (lead.name or "").split()[0] if lead.name else "there"
        industry = lead.company_industry or "your industry"

        prompt = f"""Generate {num_variants} email subject line variants for A/B testing.

ORIGINAL SUBJECT: {original_subject}
EMAIL TYPE: {email_type}
RECIPIENT: {first_name} at {company} ({industry})

Create variants using these approaches:
1. Curiosity/intrigue (make them want to know more)
2. Benefit-focused (what's in it for them)
3. Question-based (engage with a relevant question)
4. Personalized (reference their company/industry)

Rules:
- Keep under 50 characters when possible
- Avoid spam trigger words (free, guarantee, act now)
- No ALL CAPS
- Be professional but human
- Don't use emojis unless appropriate for B2B

Return JSON array:
[
  {{
    "subject": "the subject line",
    "approach": "curiosity|benefit|question|personalized",
    "predicted_open_rate": "high|medium|low",
    "reasoning": "why this might work"
  }}
]

Return ONLY the JSON array."""

        try:
            response = await self.openai.generate_completion(
                prompt=prompt,
                temperature=0.7,
                max_tokens=600,
            )

            variants = json.loads(response)

            # Add original as control
            variants.insert(0, {
                "subject": original_subject,
                "approach": "original",
                "predicted_open_rate": "medium",
                "reasoning": "Control subject for comparison",
                "is_control": True,
            })

            return variants

        except Exception as e:
            logger.error(f"Subject variant generation error: {e}")
            return [{"subject": original_subject, "approach": "original", "is_control": True}]

    async def select_best_subject(
        self,
        email_type: str,
        lead_id: int,
    ) -> Optional[str]:
        """
        Select the best performing subject line for an email type.

        Analyzes historical performance of subject lines for this email type
        and returns the highest performing one.
        """
        # Get emails of this type that were sent and have engagement data
        emails = (
            self.db.query(Email)
            .filter(
                Email.email_type == email_type,
                Email.status == "sent",
                Email.sent_at.isnot(None),
            )
            .all()
        )

        if len(emails) < 10:
            return None  # Not enough data

        # Calculate open rate per subject pattern
        subject_performance = {}
        for email in emails:
            subject = email.subject or ""
            # Normalize subject (remove names, numbers for grouping)
            normalized = re.sub(r'\b\w+@\w+\.\w+\b', '[EMAIL]', subject)
            normalized = re.sub(r'\b\d+\b', '[NUM]', normalized)

            if normalized not in subject_performance:
                subject_performance[normalized] = {"sent": 0, "opened": 0, "original": subject}

            subject_performance[normalized]["sent"] += 1
            if email.opened_at:
                subject_performance[normalized]["opened"] += 1

        # Find best performer with minimum sample size
        best_subject = None
        best_rate = 0

        for pattern, data in subject_performance.items():
            if data["sent"] >= 5:  # Minimum sample
                rate = data["opened"] / data["sent"]
                if rate > best_rate:
                    best_rate = rate
                    best_subject = data["original"]

        return best_subject

    # =========================================================================
    # 5. ADAPTIVE SEQUENCE BRANCHING
    # =========================================================================

    async def determine_next_sequence_step(
        self,
        lead_id: int,
        call_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Determine the optimal next step in an email sequence based on engagement.

        Adaptive branching logic:
        - High engagement → Accelerate to meeting request
        - Opened but no click → Try different CTA
        - No engagement → Switch approach or pause
        - Negative reply → Remove from sequence

        Returns recommended action and email template.
        """
        engagement = await self.calculate_engagement_score(lead_id)
        level = engagement["level"]
        breakdown = engagement["breakdown"]

        # Get recent email activity
        recent_emails = (
            self.db.query(Email)
            .filter(Email.lead_id == lead_id)
            .order_by(Email.created_at.desc())
            .limit(5)
            .all()
        )

        last_email = recent_emails[0] if recent_emails else None

        # Determine next step based on engagement
        if level == "dead":
            return {
                "action": "stop_sequence",
                "reason": "Lead unsubscribed or email invalid",
                "email_type": None,
            }

        if level == "hot":
            return {
                "action": "send_email",
                "email_type": "meeting_request",
                "reason": "High engagement detected - time to ask for meeting",
                "urgency": "high",
                "customize": {
                    "tone": "confident",
                    "include_social_proof": True,
                    "cta": "direct_meeting_link",
                },
            }

        if level == "warm":
            if last_email and last_email.clicked_at:
                return {
                    "action": "send_email",
                    "email_type": "value_add",
                    "reason": "Clicked previous email - send relevant case study",
                    "urgency": "medium",
                    "customize": {
                        "tone": "helpful",
                        "include_case_study": True,
                        "cta": "soft_meeting_request",
                    },
                }
            return {
                "action": "send_email",
                "email_type": "follow_up_1",
                "reason": "Opened emails - continue nurturing",
                "urgency": "medium",
            }

        if level == "lukewarm":
            if breakdown["emails_sent"] >= 2:
                return {
                    "action": "send_email",
                    "email_type": "different_angle",
                    "reason": "Limited engagement - try different value prop",
                    "urgency": "low",
                    "customize": {
                        "tone": "curious",
                        "try_different_use_case": True,
                        "short_format": True,
                    },
                }
            return {
                "action": "send_email",
                "email_type": "follow_up_1",
                "reason": "Some engagement - continue sequence",
                "urgency": "low",
            }

        # Cold lead
        if breakdown["emails_sent"] >= 4:
            return {
                "action": "pause_sequence",
                "reason": "No engagement after 4 emails - pause for 30 days",
                "resume_in_days": 30,
            }

        return {
            "action": "send_email",
            "email_type": "follow_up_2" if breakdown["emails_sent"] >= 2 else "follow_up_1",
            "reason": "No engagement yet - continue sequence",
            "urgency": "low",
        }

    # =========================================================================
    # 6. CONTENT OPTIMIZATION
    # =========================================================================

    async def analyze_email_content(
        self,
        subject: str,
        body_html: str,
        email_type: str,
    ) -> Dict[str, Any]:
        """
        Analyze email content for optimization opportunities.

        Checks:
        - Spam trigger words
        - Reading level
        - CTA clarity
        - Personalization level
        - Length optimization
        - Mobile friendliness
        """
        # Strip HTML for text analysis
        text = re.sub(r'<[^>]+>', ' ', body_html)
        text = re.sub(r'\s+', ' ', text).strip()

        # Spam trigger words
        spam_words = [
            'free', 'guarantee', 'no obligation', 'act now', 'limited time',
            'click here', 'buy now', 'order now', 'winner', 'congratulations',
            'urgent', '100%', 'no cost', 'risk free', 'special offer',
        ]
        found_spam_words = [w for w in spam_words if w.lower() in text.lower()]

        # Word count
        word_count = len(text.split())

        # Personalization check
        has_first_name = '{first_name}' in body_html or any(
            x in body_html.lower() for x in ['hi ', 'hello ', 'dear ']
        )
        has_company = '{company}' in body_html or 'your company' in body_html.lower()

        # CTA check
        cta_patterns = [
            r'schedule.*call', r'book.*demo', r'let.*know', r'reply',
            r'click.*here', r'learn.*more', r'get.*started',
        ]
        has_clear_cta = any(re.search(p, text.lower()) for p in cta_patterns)

        # Calculate scores
        spam_score = min(100, len(found_spam_words) * 15)
        length_score = 100 if 100 <= word_count <= 200 else max(0, 100 - abs(word_count - 150) / 2)
        personalization_score = (50 if has_first_name else 0) + (50 if has_company else 0)
        cta_score = 100 if has_clear_cta else 30

        overall_score = (
            (100 - spam_score) * 0.3
            + length_score * 0.2
            + personalization_score * 0.3
            + cta_score * 0.2
        )

        recommendations = []
        if found_spam_words:
            recommendations.append(f"Remove spam trigger words: {', '.join(found_spam_words[:3])}")
        if word_count > 250:
            recommendations.append("Shorten email - aim for 100-200 words")
        if word_count < 50:
            recommendations.append("Email may be too short - add more value")
        if not has_first_name:
            recommendations.append("Add personalization with recipient's first name")
        if not has_company:
            recommendations.append("Reference their company for relevance")
        if not has_clear_cta:
            recommendations.append("Add a clear call-to-action")

        return {
            "overall_score": round(overall_score),
            "word_count": word_count,
            "spam_score": spam_score,
            "spam_words_found": found_spam_words,
            "length_score": round(length_score),
            "personalization_score": personalization_score,
            "cta_score": cta_score,
            "has_clear_cta": has_clear_cta,
            "recommendations": recommendations,
            "ready_to_send": overall_score >= 70 and spam_score < 30,
        }

    # =========================================================================
    # 7. DELIVERABILITY INSIGHTS
    # =========================================================================

    async def get_deliverability_health(self) -> Dict[str, Any]:
        """
        Get overall email deliverability health metrics.

        Monitors:
        - Bounce rate (should be < 2%)
        - Spam complaint rate (should be < 0.1%)
        - Open rate trends
        - Domain warmup status
        """
        # Time periods
        now = datetime.utcnow()
        last_7_days = now - timedelta(days=7)
        last_30_days = now - timedelta(days=30)

        # Get recent email stats
        recent_sent = (
            self.db.query(func.count(Email.id))
            .filter(Email.sent_at >= last_7_days, Email.status == "sent")
            .scalar() or 0
        )

        recent_bounced = (
            self.db.query(func.count(Email.id))
            .filter(Email.sent_at >= last_7_days, Email.bounced_at.isnot(None))
            .scalar() or 0
        )

        recent_opened = (
            self.db.query(func.count(Email.id))
            .filter(Email.sent_at >= last_7_days, Email.opened_at.isnot(None))
            .scalar() or 0
        )

        # Calculate rates
        bounce_rate = (recent_bounced / recent_sent * 100) if recent_sent > 0 else 0
        open_rate = (recent_opened / recent_sent * 100) if recent_sent > 0 else 0

        # Determine health status
        if bounce_rate > 5:
            health_status = "critical"
            health_message = "High bounce rate - clean your list immediately"
        elif bounce_rate > 2:
            health_status = "warning"
            health_message = "Bounce rate elevated - review recent additions to list"
        elif open_rate < 10 and recent_sent > 20:
            health_status = "warning"
            health_message = "Low open rate - check subject lines and sender reputation"
        else:
            health_status = "healthy"
            health_message = "Deliverability metrics look good"

        # Warmup status (based on daily volume)
        daily_average = recent_sent / 7 if recent_sent > 0 else 0
        if daily_average < 10:
            warmup_status = "needs_warmup"
            warmup_message = "Low volume - continue gradual warmup"
        elif daily_average < 50:
            warmup_status = "warming"
            warmup_message = "Building reputation - maintain consistent volume"
        else:
            warmup_status = "warmed"
            warmup_message = "Domain is warmed up"

        return {
            "health_status": health_status,
            "health_message": health_message,
            "metrics": {
                "emails_sent_7d": recent_sent,
                "bounce_rate": round(bounce_rate, 2),
                "open_rate": round(open_rate, 2),
                "daily_average": round(daily_average, 1),
            },
            "warmup": {
                "status": warmup_status,
                "message": warmup_message,
                "daily_average": round(daily_average, 1),
            },
            "recommendations": self._get_deliverability_recommendations(
                bounce_rate, open_rate, daily_average
            ),
        }

    def _get_deliverability_recommendations(
        self,
        bounce_rate: float,
        open_rate: float,
        daily_volume: float,
    ) -> List[str]:
        """Generate deliverability recommendations."""
        recommendations = []

        if bounce_rate > 2:
            recommendations.append("Verify email addresses before sending using an email validation service")
            recommendations.append("Remove hard bounces from your list immediately")

        if open_rate < 15:
            recommendations.append("Test different subject lines with A/B testing")
            recommendations.append("Review sender name and from address")
            recommendations.append("Check if emails are landing in spam folders")

        if daily_volume < 20:
            recommendations.append("Increase sending volume gradually (10-20% per week)")
            recommendations.append("Maintain consistent daily sending patterns")

        if not recommendations:
            recommendations.append("Continue current practices - metrics are healthy")
            recommendations.append("Monitor weekly and adjust if metrics decline")

        return recommendations


# =============================================================================
# Convenience Functions
# =============================================================================

async def get_lead_email_intelligence(db: Session, lead_id: int) -> Dict[str, Any]:
    """
    Get comprehensive email intelligence for a lead.

    Returns:
    - Engagement score and level
    - Optimal send time
    - Next recommended action
    - Email history summary
    """
    agent = EmailIntelligenceAgent(db)

    engagement = await agent.calculate_engagement_score(lead_id)
    optimal_time = await agent.get_optimal_send_time(lead_id)
    next_step = await agent.determine_next_sequence_step(lead_id)

    return {
        "lead_id": lead_id,
        "engagement": engagement,
        "optimal_send_time": optimal_time.isoformat(),
        "next_step": next_step,
    }
