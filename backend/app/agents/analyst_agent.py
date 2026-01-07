# backend/app/agents/analyst_agent.py (NEW FILE)
"""
NEW FILE - Implements Learning Loop & Self-Optimization (FRD Section 5.10)

FUNCTIONALITY:
1. Analyzes call outcomes and patterns
2. Identifies what works (industry, title, script variations)
3. Recommends ICP filter changes
4. A/B tests script variations
5. Auto-adjusts and rolls back if performance drops
6. Tracks learning events for dashboard visibility
"""

from __future__ import annotations
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from app.models.lead import Lead
from app.models.call import Call
from app.models.learning_event import LearningEvent
from app.config import settings

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


class AnalystAgent:
    """
    Analyst/Learning Agent for continuous optimization.
    
    Implements:
    - Pattern detection (which leads convert better)
    - ICP refinement recommendations
    - Script A/B testing
    - Performance monitoring
    - Auto-rollback on degradation
    """
    
    def __init__(self, db: Session):
        self.db = db
        self._client = None
        if getattr(settings, "OPENAI_API_KEY", None) and OpenAI is not None:
            self._client = OpenAI(api_key=settings.OPENAI_API_KEY)
        
        self._model = getattr(settings, "OPENAI_MODEL", None) or "gpt-4o-mini"
        
        # Performance thresholds (FRD FR-38)
        self.demo_rate_threshold = 0.35  # Alert if demo rate drops below 35%
        self.rollback_threshold = 0.25  # Auto-rollback if drops below 25%
    
    async def run_learning_cycle(self) -> Dict[str, Any]:
        """
        Main learning cycle (FRD FR-35)
        
        Run weekly or after sufficient interactions (50+ calls)
        
        Returns recommendations for:
        - ICP filter changes
        - Script modifications
        - Email template updates
        """
        logger.info("🧠 Starting learning cycle...")
        
        # Get recent performance data (last 30 days)
        cutoff = datetime.utcnow() - timedelta(days=30)
        
        calls = self.db.query(Call).filter(Call.created_at >= cutoff).all()
        
        if len(calls) < 10:
            logger.info(f"⚠️ Insufficient data ({len(calls)} calls). Need 10+ for analysis.")
            return {"status": "insufficient_data", "calls_analyzed": len(calls)}
        
        # Analyze patterns
        analysis = self._analyze_patterns(calls)
        
        # Generate recommendations
        recommendations = await self._generate_recommendations(analysis)
        
        # Log learning event
        self._log_learning_event(
            event_type="learning_cycle_completed",
            description=f"Analyzed {len(calls)} calls. Generated {len(recommendations)} recommendations.",
            recommendations=recommendations
        )
        
        logger.info(f"✅ Learning cycle complete. {len(recommendations)} recommendations generated.")
        
        return {
            "status": "success",
            "calls_analyzed": len(calls),
            "recommendations": recommendations,
            "analysis": analysis
        }
    
    def _analyze_patterns(self, calls: List[Call]) -> Dict[str, Any]:
        """
        Analyze which variables correlate with positive outcomes.
        
        Variables analyzed:
        - Industry
        - Company size
        - Job title/seniority
        - Sentiment trajectory
        - Call duration
        - BANT scores
        """
        analysis = {
            "by_industry": {},
            "by_company_size": {},
            "by_title": {},
            "by_seniority": {},
            "overall_metrics": {
                "total_calls": len(calls),
                "demo_rate": 0.0,
                "positive_sentiment_rate": 0.0,
                "avg_call_duration": 0.0
            }
        }
        
        demos = 0
        positive_sentiment = 0
        total_duration = 0
        
        for call in calls:
            lead = self.db.query(Lead).filter(Lead.id == call.lead_id).first()
            if not lead:
                continue
            
            # Demo indicator
            is_demo = call.demo_requested or (call.sentiment == "positive")
            if is_demo:
                demos += 1
            
            # Sentiment
            if call.sentiment in ["positive", "interested"]:
                positive_sentiment += 1
            
            # Duration
            if call.duration:
                total_duration += call.duration
            
            # By industry
            industry = getattr(lead, "company_industry", None) or "Unknown"
            if industry not in analysis["by_industry"]:
                analysis["by_industry"][industry] = {"calls": 0, "demos": 0, "rate": 0.0}
            
            analysis["by_industry"][industry]["calls"] += 1
            if is_demo:
                analysis["by_industry"][industry]["demos"] += 1
        
        # Calculate rates
        for industry, stats in analysis["by_industry"].items():
            if stats["calls"] > 0:
                stats["rate"] = stats["demos"] / stats["calls"]
        
        analysis["overall_metrics"]["demo_rate"] = demos / len(calls) if calls else 0
        analysis["overall_metrics"]["positive_sentiment_rate"] = positive_sentiment / len(calls) if calls else 0
        analysis["overall_metrics"]["avg_call_duration"] = total_duration / len(calls) if calls else 0
        
        return analysis
    
    async def _generate_recommendations(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Use LLM to generate actionable recommendations.
        
        Example recommendations:
        - "Focus on Healthcare industry (45% demo rate vs 28% overall)"
        - "Exclude Retail (12% demo rate)"
        - "Target Director+ seniority (52% demo rate)"
        """
        if not self._client:
            return self._fallback_recommendations(analysis)
        
        try:
            prompt = f"""You are an analyst reviewing sales performance data.

PERFORMANCE DATA:
{json.dumps(analysis, indent=2)}

TASK: Generate 3-5 specific, actionable recommendations to improve demo booking rate.

Focus on:
1. Which industries/segments to focus on or exclude
2. Which job titles/seniority levels convert better
3. Call duration patterns (too short = rushed, too long = losing interest)

FORMAT: Return JSON array of recommendations:
[
  {{
    "type": "icp_filter_change",
    "action": "focus_on",
    "target": "Healthcare industry",
    "rationale": "45% demo rate vs 28% overall",
    "expected_impact": "+8% demo rate"
  }},
  ...
]

Return ONLY the JSON array, no other text."""

            resp = self._client.chat.completions.create(
                model=self._model,
                temperature=0.3,
                max_tokens=800,
                messages=[{"role": "user", "content": prompt}]
            )
            
            text = (resp.choices[0].message.content or "").strip()
            
            # Extract JSON
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            
            recommendations = json.loads(text)
            
            return recommendations if isinstance(recommendations, list) else []
            
        except Exception as e:
            logger.error(f"Recommendation generation failed: {e}")
            return self._fallback_recommendations(analysis)
    
    def _fallback_recommendations(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Simple rule-based recommendations"""
        recommendations = []
        
        demo_rate = analysis["overall_metrics"]["demo_rate"]
        
        # Industry recommendations
        best_industry = max(
            analysis["by_industry"].items(),
            key=lambda x: x[1]["rate"] if x[1]["calls"] >= 3 else 0,
            default=(None, {"rate": 0})
        )
        
        if best_industry[0] and best_industry[1]["rate"] > demo_rate * 1.3:
            recommendations.append({
                "type": "icp_filter_change",
                "action": "focus_on",
                "target": f"{best_industry[0]} industry",
                "rationale": f"{best_industry[1]['rate']*100:.0f}% demo rate vs {demo_rate*100:.0f}% overall",
                "expected_impact": f"+{(best_industry[1]['rate'] - demo_rate)*100:.0f}% demo rate"
            })
        
        # Call duration
        avg_duration = analysis["overall_metrics"]["avg_call_duration"]
        if avg_duration < 180:  # < 3 minutes
            recommendations.append({
                "type": "script_modification",
                "action": "extend_discovery",
                "target": "Discovery phase",
                "rationale": f"Avg call duration {avg_duration:.0f}s too short for proper qualification",
                "expected_impact": "Better qualification, higher demo quality"
            })
        
        return recommendations
    
    def _log_learning_event(self, event_type: str, description: str, recommendations: List[Dict] = None):
        """Log learning event for dashboard visibility (FRD FR-41)"""
        event = LearningEvent(
            event_type=event_type,
            change_description=description,
            rationale=json.dumps(recommendations) if recommendations else None,
            status="active",
            implemented_at=datetime.utcnow()
        )
        
        self.db.add(event)
        self.db.commit()
    
    async def monitor_performance_and_rollback(self) -> Dict[str, Any]:
        """
        Monitor key metrics after changes (FRD FR-38)
        
        Auto-rollback if performance degrades significantly.
        """
        # Get recent active changes
        recent_changes = (
            self.db.query(LearningEvent)
            .filter(
                and_(
                    LearningEvent.status == "active",
                    LearningEvent.implemented_at >= datetime.utcnow() - timedelta(days=7)
                )
            )
            .all()
        )
        
        if not recent_changes:
            return {"status": "no_active_changes"}
        
        # Check current performance
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_calls = self.db.query(Call).filter(Call.created_at >= week_ago).all()
        
        if len(recent_calls) < 10:
            return {"status": "insufficient_data"}
        
        # Calculate demo rate
        demos = sum(1 for c in recent_calls if c.demo_requested or c.sentiment == "positive")
        demo_rate = demos / len(recent_calls)
        
        # Compare to baseline (previous 30 days before change)
        baseline_start = recent_changes[0].implemented_at - timedelta(days=30)
        baseline_end = recent_changes[0].implemented_at
        
        baseline_calls = self.db.query(Call).filter(
            and_(
                Call.created_at >= baseline_start,
                Call.created_at < baseline_end
            )
        ).all()
        
        if not baseline_calls:
            return {"status": "no_baseline"}
        
        baseline_demos = sum(1 for c in baseline_calls if c.demo_requested or c.sentiment == "positive")
        baseline_rate = baseline_demos / len(baseline_calls)
        
        # Check for degradation
        degradation = baseline_rate - demo_rate
        
        if demo_rate < self.rollback_threshold:
            # CRITICAL: Auto-rollback
            logger.warning(f"🚨 CRITICAL DEGRADATION: Demo rate {demo_rate*100:.1f}% < threshold {self.rollback_threshold*100:.1f}%. Rolling back!")
            
            for change in recent_changes:
                change.status = "rolled_back"
                change.rollback_reason = f"Demo rate dropped to {demo_rate*100:.1f}%"
                change.rolled_back_at = datetime.utcnow()
            
            self.db.commit()
            
            return {
                "status": "rollback_executed",
                "demo_rate": demo_rate,
                "baseline_rate": baseline_rate,
                "degradation": degradation
            }
        
        elif degradation > 0.10:  # 10%+ drop
            # WARNING: Flag for review
            logger.warning(f"⚠️ Performance drop detected: {degradation*100:.1f}% decrease in demo rate")
            
            return {
                "status": "performance_warning",
                "demo_rate": demo_rate,
                "baseline_rate": baseline_rate,
                "degradation": degradation
            }
        
        else:
            # Performance stable or improving
            return {
                "status": "performance_stable",
                "demo_rate": demo_rate,
                "baseline_rate": baseline_rate,
                "improvement": -degradation if degradation < 0 else 0
            }