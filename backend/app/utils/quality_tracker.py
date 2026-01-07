# backend/app/utils/quality_tracker.py
"""
Response quality metrics tracker.
Measures sentiment, conversation markers, and response quality to ensure
optimization doesn't degrade call quality.
"""

import re
from typing import Dict, Optional, Tuple
from app.utils.logger import logger


class ResponseQualityTracker:
    """
    Track quality metrics for agent responses.
    Ensures quick responses and caching don't degrade conversation quality.
    """

    # Sentiment markers
    POSITIVE_MARKERS = [
        "makes sense", "great", "perfect", "exactly", "agreed",
        "sounds good", "interested", "like this", "love that",
        "that's helpful", "very useful", "absolutely"
    ]

    NEGATIVE_MARKERS = [
        "not interested", "don't need", "waste of time", "irrelevant",
        "boring", "confusing", "unhelpful", "bad", "terrible"
    ]

    ENGAGEMENT_MARKERS = [
        "how", "when", "what", "tell me", "show me", "explain",
        "interested", "curious", "question", "ask"
    ]

    OBJECTION_MARKERS = [
        "expensive", "cost", "budget", "can't afford", "too much",
        "not now", "later", "already have", "using", "competitor"
    ]

    def __init__(self):
        self.metrics: Dict = {
            "total_responses": 0,
            "quick_responses": 0,
            "cached_responses": 0,
            "llm_responses": 0,
            "avg_length": 0,
            "avg_sentiment_score": 0,
            "question_density": 0,
            "engagement_level": 0,
            "objection_detection_accuracy": 0,
        }
        self.quality_history: list = []

    def analyze_response(
        self,
        response_text: str,
        response_type: str,  # "quick", "cached", "llm"
        user_input: str,
    ) -> Dict:
        """
        Analyze a single response for quality metrics.

        Args:
            response_text: The agent's response
            response_type: Type of response (quick/cached/llm)
            user_input: User input that prompted the response

        Returns:
            Quality metrics dict with scores and analysis
        """
        response_lower = response_text.lower().strip()
        user_lower = user_input.lower().strip()

        # 1. Response length (optimal: 50-150 words)
        word_count = len(response_text.split())
        length_score = self._score_length(word_count)

        # 2. Sentiment analysis
        sentiment_score = self._analyze_sentiment(response_lower)

        # 3. Question density (optimal: 0.33-0.67 questions per sentence)
        question_count = response_text.count("?")
        sentence_count = max(1, len(re.split(r"[.!?]", response_text)) - 1)
        question_density = question_count / max(1, sentence_count)
        density_score = self._score_question_density(question_density)

        # 4. Engagement markers
        engagement_score = self._count_markers(response_lower, self.ENGAGEMENT_MARKERS)

        # 5. Conversation coherence (does response relate to user input?)
        coherence_score = self._score_coherence(response_lower, user_lower)

        # 6. Overall quality score (0-100)
        overall_score = (
            length_score * 0.20 +
            sentiment_score * 0.25 +
            density_score * 0.20 +
            engagement_score * 0.15 +
            coherence_score * 0.20
        )

        metrics = {
            "response_type": response_type,
            "word_count": word_count,
            "length_score": round(length_score, 2),
            "sentiment_score": round(sentiment_score, 2),
            "question_density": round(question_density, 2),
            "question_density_score": round(density_score, 2),
            "engagement_score": round(engagement_score, 2),
            "coherence_score": round(coherence_score, 2),
            "overall_quality_score": round(overall_score, 2),
        }

        self.quality_history.append(metrics)
        self._update_aggregate_metrics(metrics)

        logger.info(f"[QUALITY] {response_type} response: overall_score={metrics['overall_quality_score']}/100")

        return metrics

    def _score_length(self, word_count: int) -> float:
        """Score response length (optimal: 50-150 words)."""
        if word_count < 20:
            return 30.0  # Too short
        if word_count < 50:
            return 70.0  # Bit short
        if word_count <= 150:
            return 100.0  # Perfect
        if word_count <= 200:
            return 80.0  # Bit long
        return 50.0  # Too long

    def _analyze_sentiment(self, response_lower: str) -> float:
        """Analyze sentiment in response (0-100)."""
        positive = sum(1 for marker in self.POSITIVE_MARKERS if marker in response_lower)
        negative = sum(1 for marker in self.NEGATIVE_MARKERS if marker in response_lower)

        if positive + negative == 0:
            return 70.0  # Neutral is acceptable

        sentiment_ratio = positive / (positive + negative)
        return min(100.0, sentiment_ratio * 100)

    def _score_question_density(self, density: float) -> float:
        """Score question density (optimal: 0.33-0.67)."""
        if density == 0:
            return 70.0  # Acceptable to have statements
        if 0.2 <= density <= 0.8:
            return 100.0  # Good question rate
        if density < 0.2:
            return 80.0  # Few questions
        return 60.0  # Too many questions

    def _count_markers(self, text: str, markers: list) -> float:
        """Count engagement markers in text (normalized 0-100)."""
        count = sum(1 for marker in markers if marker in text)
        return min(100.0, count * 20)  # Each marker = 20 points, capped at 100

    def _score_coherence(self, response: str, user_input: str) -> float:
        """Score if response relates to user input."""
        # Check for overlap in key words
        response_words = set(response.split())
        user_words = set(user_input.split())

        # Remove common words
        common = {"is", "are", "the", "a", "an", "to", "of", "in", "for", "and", "or"}
        response_words -= common
        user_words -= common

        if not user_words:
            return 80.0  # Can't assess, assume okay

        overlap = len(response_words & user_words)
        coherence_ratio = overlap / len(user_words)

        return min(100.0, max(60.0, coherence_ratio * 100))  # 60-100 range

    def _update_aggregate_metrics(self, metrics: Dict) -> None:
        """Update running aggregate metrics."""
        self.metrics["total_responses"] += 1

        response_type = metrics["response_type"]
        if response_type == "quick":
            self.metrics["quick_responses"] += 1
        elif response_type == "cached":
            self.metrics["cached_responses"] += 1
        else:
            self.metrics["llm_responses"] += 1

        # Update rolling averages
        total = self.metrics["total_responses"]
        self.metrics["avg_length"] = (
            (self.metrics["avg_length"] * (total - 1) + metrics["word_count"]) / total
        )
        self.metrics["avg_sentiment_score"] = (
            (self.metrics["avg_sentiment_score"] * (total - 1) + metrics["sentiment_score"]) / total
        )
        self.metrics["question_density"] = (
            (self.metrics["question_density"] * (total - 1) + metrics["question_density"]) / total
        )
        self.metrics["engagement_level"] = (
            (self.metrics["engagement_level"] * (total - 1) + metrics["engagement_score"]) / total
        )

    def get_quality_report(self) -> Dict:
        """Get quality metrics report."""
        if not self.quality_history:
            return {
                "status": "no_data",
                "message": "No quality metrics recorded yet"
            }

        total = self.metrics["total_responses"]
        quick_pct = (self.metrics["quick_responses"] / total * 100) if total > 0 else 0
        cached_pct = (self.metrics["cached_responses"] / total * 100) if total > 0 else 0
        llm_pct = (self.metrics["llm_responses"] / total * 100) if total > 0 else 0

        # Calculate average overall score from recent responses
        recent_scores = [m["overall_quality_score"] for m in self.quality_history[-100:]]
        avg_overall_score = sum(recent_scores) / len(recent_scores) if recent_scores else 0

        return {
            "total_responses": total,
            "response_distribution": {
                "quick_percent": round(quick_pct, 1),
                "cached_percent": round(cached_pct, 1),
                "llm_percent": round(llm_pct, 1),
            },
            "quality_metrics": {
                "avg_overall_score": round(avg_overall_score, 2),
                "avg_length_words": round(self.metrics["avg_length"], 1),
                "avg_sentiment_score": round(self.metrics["avg_sentiment_score"], 2),
                "avg_question_density": round(self.metrics["question_density"], 2),
                "avg_engagement_level": round(self.metrics["engagement_level"], 2),
            },
            "quality_status": self._assess_quality_status(avg_overall_score),
        }

    def _assess_quality_status(self, score: float) -> str:
        """Assess overall quality based on score."""
        if score >= 85:
            return "excellent"
        if score >= 75:
            return "good"
        if score >= 65:
            return "acceptable"
        if score >= 50:
            return "degraded"
        return "poor"

    def check_quality_alert(self, baseline_score: float = 75.0) -> Optional[Dict]:
        """
        Check if quality has degraded below baseline.
        Returns alert dict if quality is concerning.
        """
        if not self.quality_history:
            return None

        recent_scores = [m["overall_quality_score"] for m in self.quality_history[-50:]]
        recent_avg = sum(recent_scores) / len(recent_scores) if recent_scores else 0

        if recent_avg < baseline_score:
            degradation = baseline_score - recent_avg
            return {
                "alert": True,
                "severity": "warning" if degradation < 10 else "critical",
                "message": f"Quality degraded by {degradation:.1f} points (baseline: {baseline_score}, current: {recent_avg:.1f})",
                "recommendation": "Review quick response templates and consider increasing LLM usage",
            }

        return None


# Global quality tracker instance
_quality_tracker = ResponseQualityTracker()


def get_quality_tracker() -> ResponseQualityTracker:
    """Get the global quality tracker instance."""
    return _quality_tracker
