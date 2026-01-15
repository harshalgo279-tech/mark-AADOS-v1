# Production Deployment Guide: Latency Optimization Suite

## Pre-Deployment Checklist

### Code Readiness
- [x] All code changes committed to git
- [x] Python syntax verified (py_compile)
- [x] No breaking API changes
- [x] Backward compatible (optimizations are optional)
- [x] No database schema changes required
- [x] No new environment variables required

### Testing
- [ ] Unit tests pass for latency_tracker, response_cache, quality_tracker
- [ ] Integration test: Full call flow with all optimizations enabled
- [ ] Load test: 50+ concurrent calls with caching enabled
- [ ] Quality test: Verify quality scores >75/100 across response types
- [ ] Rollback test: Verify system works with optimizations disabled

### Documentation
- [x] LATENCY_OPTIMIZATIONS.md - Technical implementation details
- [x] LATENCY_DASHBOARD.md - Monitoring & metrics
- [x] QUALITY_METRICS.md - Quality framework & analysis
- [x] ITERATION_4_SUMMARY.md - Complete iteration overview
- [ ] PRODUCTION_DEPLOYMENT_GUIDE.md - This file
- [ ] Runbook: How to respond to quality alerts
- [ ] Runbook: How to roll back optimizations

### Infrastructure
- [ ] Monitoring system configured (DataDog/CloudWatch/etc.)
- [ ] Log aggregation set up (ELK/Splunk/etc.)
- [ ] Alerts configured for quality degradation (baseline: 75/100)
- [ ] Latency dashboard created
- [ ] Backup plan documented (rollback procedure)

---

## Deployment Steps

### Phase 1: Shadow Mode (Day 1-3)
**Goal:** Validate optimizations work without affecting users

1. **Deploy code to staging environment**
   ```bash
   git pull origin main
   python -m pip install -r requirements.txt
   pytest tests/  # Run test suite
   ```

2. **Enable all optimizations in staging**
   - Set environment: `LATENCY_OPTIMIZATION_MODE=shadow`
   - All logs go to monitoring system
   - No user traffic affected

3. **Run synthetic tests**
   ```bash
   # Test quick responses, caching, quality tracking
   pytest tests/test_optimizations.py -v
   pytest tests/test_quality_metrics.py -v
   ```

4. **Monitor metrics**
   - Check latency logs: `grep [LATENCY] logs/*.log`
   - Check quality logs: `grep [QUALITY] logs/*.log`
   - Verify no errors in cache or response handling

5. **Success criteria:**
   - ✅ No errors in optimization code
   - ✅ Latency metrics logged correctly
   - ✅ Quality tracking functional
   - ✅ Cache hit rates reasonable

---

### Phase 2: Canary Deployment (Day 4-7)
**Goal:** Gradually roll out to 10-25% of production traffic

1. **Deploy to production (canary)**
   ```bash
   # Use canary deployment (10% traffic)
   kubectl set image deployment/voice-agent \
     voice-agent=voice-agent:optimized-v1.0 --record
   ```

2. **Monitor canary metrics**
   - Average latency: Target <1.5s
   - Quality score: Target >75/100
   - Error rate: Should not increase
   - Cache hit rate: Target >35%

3. **SLA Monitoring (Real-Time)**
   - Latency:
     - Alert if >2.5s for 5+ consecutive calls
     - Auto-rollback if >3s for 10+ calls
   - Quality:
     - Alert if <70/100 for 50-call window
     - Log incident if <65/100
   - API calls:
     - Should drop 60-70% vs baseline

4. **Success criteria:**
   - ✅ Canary latency: <1.5s average
   - ✅ Canary quality: >75/100 average
   - ✅ No error rate increase
   - ✅ Cache hit rate: 35-45%

---

### Phase 3: Ramp-Up Deployment (Day 8-14)
**Goal:** Gradually increase to 100% of production traffic

1. **Increase traffic gradually**
   ```bash
   # Day 8: 25% traffic
   # Day 10: 50% traffic
   # Day 12: 75% traffic
   # Day 14: 100% traffic
   ```

2. **Continue monitoring**
   - Latency should remain <1.5s
   - Quality should remain >75/100
   - Cache hit rate stabilizes around 40%

3. **Watch for edge cases**
   - Are there specific states/inputs with low quality?
   - Are there timeouts happening at scale?
   - Are there cache coherence issues?

4. **Success criteria:**
   - ✅ Full traffic at <1.5s latency
   - ✅ Quality maintained >75/100
   - ✅ No performance degradation over time
   - ✅ Cache effectiveness stable

---

### Phase 4: Stabilization (Day 15+)
**Goal:** Monitor for long-term stability and performance

1. **Continuous monitoring**
   - Daily: Review quality metrics report
   - Weekly: Analyze latency trends
   - Monthly: Generate performance report

2. **Optimization tuning**
   - If quality <75/100: Adjust quick response templates
   - If quality >85/100: Could reduce LLM calls further
   - If cache hit <35%: Increase TTL or adjust caching strategy

3. **Documentation**
   - Update runbooks based on learnings
   - Document any edge cases found
   - Create incident response procedures

---

## Environment Variables (Optional)

None required for basic operation. Optional for advanced control:

```bash
# Shadow mode (deployment phase)
LATENCY_OPTIMIZATION_MODE=shadow    # Default: disabled
LATENCY_OPTIMIZATION_MODE=enabled   # Full optimization

# Tuning parameters
RESPONSE_CACHE_TTL_SECONDS=3600     # Default: 3600 (1 hour)
QUALITY_BASELINE_SCORE=75.0         # Default: 75.0
QUALITY_ALERT_THRESHOLD=5.0         # Default: 5.0 points
```

---

## Monitoring & Alerting Setup

### Key Metrics to Monitor

```
[LATENCY] total_ms: Should average 1.0-1.5s
[CACHE] Cache hit rate: Should be 35-45%
[QUALITY] overall_quality_score: Should be >75/100
[TELEMETRY] Turn complete: Includes all metrics above
```

### Sample Alert Rules

**DataDog:**
```python
# Latency alert
alert = {
    "name": "Voice Agent Latency High",
    "query": 'avg:custom.voice.latency_ms{service:voice-agent} > 2500',
    "thresholds": {"critical": 2500, "warning": 2000},
    "message": "{{value}}ms latency detected. Investigate {{env}} cluster."
}

# Quality alert
alert = {
    "name": "Voice Quality Degraded",
    "query": 'avg:custom.voice.quality_score{service:voice-agent} < 70',
    "thresholds": {"critical": 70, "warning": 75},
    "message": "Quality score {{value}}/100. Review response templates."
}
```

**CloudWatch:**
```json
{
  "MetricAlarms": [
    {
      "AlarmName": "VoiceAgentLatencyHigh",
      "MetricName": "voice_agent_latency_ms",
      "Threshold": 2500,
      "ComparisonOperator": "GreaterThanThreshold",
      "EvaluationPeriods": 2,
      "Period": 60
    },
    {
      "AlarmName": "VoiceAgentQualityDegraded",
      "MetricName": "voice_agent_quality_score",
      "Threshold": 70,
      "ComparisonOperator": "LessThanThreshold",
      "EvaluationPeriods": 1,
      "Period": 300
    }
  ]
}
```

### Dashboard Queries

**Latency Dashboard:**
```sql
-- Average latency over time
SELECT timestamp, avg(total_ms) as latency_ms
FROM latency_logs
WHERE service = 'voice_agent'
GROUP BY timestamp ORDER BY timestamp DESC
LIMIT 100

-- Latency by response type
SELECT response_type, avg(total_ms) as avg_latency, count(*) as calls
FROM latency_logs
WHERE service = 'voice_agent'
GROUP BY response_type

-- 95th percentile latency
SELECT PERCENTILE(total_ms, 0.95) as p95_latency
FROM latency_logs
WHERE service = 'voice_agent'
```

**Quality Dashboard:**
```sql
-- Average quality score over time
SELECT timestamp, avg(overall_quality_score) as quality
FROM quality_logs
WHERE service = 'voice_agent'
GROUP BY timestamp ORDER BY timestamp DESC
LIMIT 100

-- Quality by response type
SELECT response_type, avg(overall_quality_score) as avg_quality
FROM quality_logs
WHERE service = 'voice_agent'
GROUP BY response_type

-- Quality alerts
SELECT COUNT(*) as alert_count
FROM quality_logs
WHERE quality_status IN ('degraded', 'poor')
AND timestamp > NOW() - INTERVAL 24 HOURS
```

---

## Rollback Procedure

If critical issues arise, follow this procedure:

### Immediate Rollback (5 min)
1. **Disable quick responses**
   ```python
   # In voice_agent.py, comment out:
   # quick_reply = try_quick_response(...)
   ```

2. **Disable response caching**
   ```python
   # In voice_agent.py, comment out:
   # cached_reply = cache.get(...)
   ```

3. **Revert LLM timeout to 10s**
   ```python
   # Revert all state timeouts to 10.0
   timeout_s=10.0  # Original value
   ```

4. **Deploy changes**
   ```bash
   git commit -m "rollback: disable optimizations"
   git push origin main
   kubectl rollout undo deployment/voice-agent
   ```

### Monitor After Rollback
- Latency should return to 3-5s baseline
- Quality should return to unmonitored baseline
- API call volume should return to normal

### Full Rollback (if needed)
```bash
# Revert to previous release
git revert <commit-hash>
git push origin main
kubectl set image deployment/voice-agent \
  voice-agent=voice-agent:previous-stable --record
```

---

## Post-Deployment: First 30 Days

### Week 1: Daily Monitoring
- ✅ Check latency metrics every 4 hours
- ✅ Monitor quality scores for degradation
- ✅ Watch for any errors in optimization code
- ✅ Verify cache hit rates

### Week 2: Stabilization
- ✅ Collect 100+ calls worth of quality data
- ✅ Analyze quality by response type
- ✅ Fine-tune quick response templates if needed
- ✅ Document any patterns or edge cases

### Week 3-4: Analysis
- ✅ Generate performance report (before vs after)
- ✅ Calculate cost savings from reduced API calls
- ✅ Document lessons learned
- ✅ Plan any Phase 2 optimizations

### Success Metrics (30 Days)
- ✅ Average latency: <1.5s (70-80% improvement)
- ✅ Quality average: >75/100
- ✅ API cost: -60-70% reduction
- ✅ Zero rollbacks due to quality issues

---

## Incident Response Playbook

### Scenario: Latency Spike (>2.5s)

**Detection:**
```
[ALERT] Voice Agent Latency High: 2850ms (threshold: 2500ms)
```

**Triage (5 min):**
1. Check if it's specific to a state or user input type
2. Check if cache hit rate dropped
3. Check if LLM timeouts are occurring
4. Check infrastructure (CPU, memory, network)

**Response Options:**
- **Temporary fix:** Increase LLM timeout from 6s → 8s
- **Root cause:** Review logs for timeout errors
- **Permanent:** Optimize problematic states

---

### Scenario: Quality Degradation (<70/100)

**Detection:**
```
[QUALITY_ALERT] Quality degraded by 8 points (baseline: 75, current: 67)
```

**Triage (5 min):**
1. Check which response types are degraded
2. Check for negative sentiment markers
3. Check if specific states are problematic

**Response Options:**
- **Quick:** Increase LLM usage (disable quick responses for affected states)
- **Medium:** Update quick response templates
- **Investigate:** Review actual responses vs LLM alternatives

---

## Success Criteria for Production

✅ **Latency:** Average <1.5s (70-80% improvement from 3-5s)
✅ **Quality:** Average >75/100 with automated alerts
✅ **Cost:** 60-70% reduction in OpenAI API calls
✅ **Reliability:** Zero critical incidents in first 30 days
✅ **Monitoring:** All metrics logged and dashboard operational

---

## Handoff Documentation

After deployment, ensure team has:
1. Access to monitoring dashboard
2. Copy of quality metrics runbook
3. Copy of incident response procedures
4. Contact list for escalation
5. Links to optimization documentation
6. Access to git repository with all changes

---

## Questions & Support

For questions about:
- **Deployment:** See "Deployment Steps" section above
- **Monitoring:** See "Monitoring & Alerting Setup" section
- **Rollback:** See "Rollback Procedure" section
- **Metrics:** See documentation files (LATENCY_DASHBOARD.md, QUALITY_METRICS.md)
- **Code:** See code comments and LATENCY_OPTIMIZATIONS.md

