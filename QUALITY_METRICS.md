# Voice Agent Quality Metrics System

## Overview

The Quality Metrics System monitors conversation quality while latency optimizations are in place. It ensures that aggressive optimization techniques (quick responses, response caching, reduced timeouts) don't degrade call quality or lead interest.

---

## Quality Scoring Framework

### Overall Quality Score (0-100)

Weighted combination of five metrics:

```
Overall Score =
  Length Score (20%) +
  Sentiment Score (25%) +
  Question Density Score (20%) +
  Engagement Score (15%) +
  Coherence Score (20%)
```

### Individual Metrics

#### 1. **Length Score (20%)**
Optimal response length for voice: 50-150 words

| Word Count | Score |
|-----------|-------|
| <20 | 30/100 (too short) |
| 20-50 | 70/100 (bit short) |
| 50-150 | 100/100 (perfect) |
| 150-200 | 80/100 (bit long) |
| >200 | 50/100 (too long) |

**Why:** Short responses feel dismissive; long responses lose the listener.

---

#### 2. **Sentiment Score (25%)**
Measures positive vs negative language markers

```
Positive Markers:
"makes sense", "great", "perfect", "exactly", "agreed",
"sounds good", "interested", "like this", "love that"

Negative Markers:
"not interested", "don't need", "waste of time",
"confusing", "unhelpful", "bad", "terrible"
```

**Scoring:**
- Neutral response (no markers): 70/100 (acceptable)
- Positive ratio: min(100, ratio × 100)
- Negative detected: Immediately degraded

**Why:** Positive sentiment keeps prospects engaged; negative language kills deals.

---

#### 3. **Question Density Score (20%)**
Ratio of questions per sentence (optimal: 0.33-0.67)

| Questions/Sentence | Score |
|------------------|-------|
| 0 (all statements) | 70/100 |
| 0.2-0.8 | 100/100 (ideal) |
| <0.2 (few questions) | 80/100 |
| >0.8 (too many) | 60/100 |

**Why:** Questions drive engagement and turn-taking. Too many feel like interrogation.

---

#### 4. **Engagement Score (15%)**
Presence of engagement markers

```
Engagement Markers (20 points each, capped at 100):
"how", "when", "what", "tell me", "show me",
"explain", "interested", "curious", "question", "ask"
```

**Why:** These words indicate conversational intent and curiosity.

---

#### 5. **Coherence Score (20%)**
Response relevance to user input

- Matches user keywords: Higher score
- Minimal overlap: 60-100 range (at least somewhat related)
- No overlap: 60/100 (generic but acceptable)

**Why:** Responses should address what the prospect said.

---

## Quality Status Classifications

| Score | Status | Action |
|-------|--------|--------|
| 85-100 | **Excellent** | ✅ Continue current strategy |
| 75-85 | **Good** | ✅ Monitor, no action needed |
| 65-75 | **Acceptable** | ⚠️ Monitor closely, review edge cases |
| 50-65 | **Degraded** | 🔴 Investigate, may need intervention |
| <50 | **Poor** | 🔴 ALERT - Review strategy |

---

## Response Type Quality Analysis

### Quick Responses (Target: >70/100 average)
**States:** 0 (opening), 1 (permission), 12 (exit)
**Risk:** Generic/formulaic responses may lack personalization

Quick response template example:
```
"Thanks for your time. Do you have a few minutes?"
- Length: 9 words (short but acceptable for quick states)
- Sentiment: neutral (70/100)
- Questions: 1/1 sentence (100/100)
- Engagement: "Do" marker (+20 = 80/100)
- Coherence: Generic but relevant (70/100)
─────────────────────────────────────
Overall: 75/100 ✅ Acceptable
```

### Cached Responses (Target: >75/100 average)
**Risk:** May not match current context if conditions change

Cached response example:
```
"Perfect. I'll ask one question about your setup, and based on that..."
- Length: 14 words (bit short)
- Sentiment: positive ("perfect") = 100/100
- Questions: 1/2 sentences = 0.5 (good)
- Engagement: High ("ask one question")
- Coherence: High (mentions user setup)
─────────────────────────────────────
Overall: 82/100 ✅ Good
```

### LLM Responses (Target: >80/100 average)
**Risk:** Lower due to diverse user inputs and complex conversational states

LLM response example:
```
"Most teams find that once they centralize the approval process, turnaround times drop by half. Does that sound like an issue for you?"
- Length: 21 words (good range)
- Sentiment: positive ("find that") = 85/100
- Questions: 1/1 (100/100)
- Engagement: "Does" + "like" = 80/100
- Coherence: Directly addresses context
─────────────────────────────────────
Overall: 86/100 ✅ Excellent
```

---

## Monitoring & Alerting

### Quality Alert Thresholds

**Baseline Score: 75/100**

```
Recent 50 calls average score < 75:
  ├─ Degradation 0-5 points: Yellow warning
  └─ Degradation >5 points: Red alert
```

### Alert Message Format
```
[QUALITY_ALERT] Quality degraded by X points (baseline: 75, current: Y) |
Review quick response templates and consider increasing LLM usage
```

### Automatic Actions
1. **Log warning** in system logs
2. **Notify monitoring** (if integrated with DataDog, CloudWatch, etc.)
3. **No automatic changes** (manual review required)

---

## API Endpoints

### Get Quality Metrics Report
```bash
GET /api/calls/quality/metrics
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "total_responses": 245,
    "response_distribution": {
      "quick_percent": 38.8,
      "cached_percent": 31.2,
      "llm_percent": 30.0
    },
    "quality_metrics": {
      "avg_overall_score": 78.5,
      "avg_length_words": 62,
      "avg_sentiment_score": 72.3,
      "avg_question_density": 0.42,
      "avg_engagement_level": 65.2
    },
    "quality_status": "good"
  }
}
```

---

## Quality Logs

All quality analysis is logged with `[QUALITY]` prefix:

```
[QUALITY] quick response: overall_score=75/100
[QUALITY] cached response: overall_score=82/100
[QUALITY] llm response: overall_score=86/100

[QUALITY_ALERT] Quality degraded by 6.5 points (baseline: 75, current: 68.5) |
Review quick response templates and consider increasing LLM usage

[TELEMETRY] Turn complete in 1200ms | Cache: {...} | Quality: good
```

---

## Quality Assurance Best Practices

### For Quick Responses
1. ✅ Keep them under 15 words (concise)
2. ✅ Include exactly 1 question per response
3. ✅ Use positive or neutral sentiment
4. ✅ Mention context from the call

### For Cached Responses
1. ✅ Monitor for context misalignment
2. ✅ Track if same response is used too frequently
3. ✅ Flag if user contradicts cached assumption
4. ✅ Refresh cache periodically (TTL: 1 hour)

### For LLM Responses
1. ✅ Maintain consistent quality bar (>80/100)
2. ✅ Monitor token efficiency
3. ✅ Track edge cases where LLM fails
4. ✅ Use for complex states (6-8, objection handling)

---

## Success Metrics

### Target Quality Distribution
| Response Type | Distribution | Avg Score | Target |
|--------------|--------------|-----------|--------|
| Quick | 35-45% | 75/100 | ✅ |
| Cached | 25-35% | 80/100 | ✅ |
| LLM | 25-35% | 85/100 | ✅ |
| **Overall Average** | **100%** | **79/100** | ✅ |

### SLA Compliance
- ✅ Average quality score: >78/100
- ✅ Minimum acceptable score: >70/100 (for 95% of responses)
- ✅ No quality alerts for >2 weeks
- ✅ Response type distribution within targets

---

## Degradation Investigation Checklist

If quality score drops below 75/100:

1. **Identify culprit response type:**
   - Quick responses degraded? → Review templates
   - Cached responses degraded? → Check cache staleness
   - LLM responses degraded? → Review timeout/model quality

2. **Analyze by state:**
   ```
   - Which states are low-quality?
   - Are there patterns? (e.g., always state 5)
   - Are specific user inputs causing issues?
   ```

3. **Review metrics:**
   - Length too short/long? → Adjust templates
   - Sentiment negative? → Review tone
   - Questions missing? → Add prompts
   - Coherence low? → Improve context

4. **Remediation options:**
   - **Quick:** Increase LLM timeout (use more for states)
   - **Medium:** Update quick response templates
   - **Long-term:** Improve LLM prompts and training

---

## Integration with Monitoring Systems

### DataDog Integration (Example)
```
# Parse [QUALITY] logs
datadog_monitors:
  - name: "Voice Quality Score Alert"
    query: logs("service:voice-agent [QUALITY]").avg("overall_quality_score") < 75
    alert_on_no_data: false
    thresholds:
      warning: 75
      critical: 70
```

### CloudWatch Metrics (Example)
```
CloudWatch Insights Query:
fields overall_quality_score
| filter metadata.service == "voice-agent"
| stats avg(overall_quality_score) as avg_quality
| filter avg_quality < 75
```

---

## Timeline & Rollout

**Week 1:** Deploy quality tracking in shadow mode (logging only, no alerts)
**Week 2-3:** Monitor quality baseline, adjust thresholds if needed
**Week 4:** Enable quality alerts with manual review required
**Week 5+:** Production monitoring with automated dashboards

