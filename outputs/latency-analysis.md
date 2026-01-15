# AADOS Voice Agent Latency Analysis Report

## Executive Summary

This report identifies **15 specific latency bottlenecks** in the AADOS voice agent system, along with estimated latency impact and optimization recommendations.

**Current End-to-End Latency Estimate**: 2,500-4,500ms per turn
**Target End-to-End Latency**: 800-1,200ms per turn

---

## Bottleneck Identification

### BOTTLENECK #1: OpenAI LLM API Call (HIGH IMPACT)

**File**: `backend/app/services/openai_service.py`
**Lines**: 60-103

**Current Implementation**:
```python
resp = await asyncio.wait_for(asyncio.to_thread(_do), timeout=timeout_s)
```

**Issue**:
- Synchronous OpenAI SDK wrapped in `asyncio.to_thread()`
- No streaming - waits for complete response
- Cold start penalty on first request

**Estimated Latency**: 1,500-3,000ms
**Impact**: HIGH

**Optimization Recommendations**:
1. Use OpenAI async client with streaming enabled
2. Implement token streaming to start TTS earlier
3. Use connection pooling for OpenAI API
4. Consider using `gpt-4o-mini-2024-07-18` for faster inference

---

### BOTTLENECK #2: OpenAI TTS Generation (HIGH IMPACT)

**File**: `backend/app/services/openai_service.py`
**Lines**: 139-221

**Current Implementation**:
```python
resp = await client.post(url, headers=headers, json=payload, timeout=timeout_s)
```

**Issue**:
- Full audio file generated before playback
- No audio streaming to Twilio
- 20-second default timeout is generous but slow

**Estimated Latency**: 800-2,000ms
**Impact**: HIGH

**Optimization Recommendations**:
1. Implement chunked audio streaming
2. Use `response_format: "opus"` for smaller files
3. Pre-generate first sentence while LLM generates rest
4. Consider ElevenLabs or Azure TTS for lower latency

---

### BOTTLENECK #3: Sequential LLM → TTS Pipeline (HIGH IMPACT)

**File**: `backend/app/api/calls.py`
**Lines**: 497-519

**Current Implementation**:
```python
reply = await agent.generate_reply(call=call, user_input=user_speech)
# ... postprocess ...
agent_audio_url = await agent.tts_audio_url(call_id=call.id, text=reply_clean)
```

**Issue**:
- TTS waits for complete LLM response
- No parallel execution for new turn
- Streaming response handler exists but not used in main path

**Estimated Latency**: Combined 2,300-5,000ms (additive)
**Impact**: HIGH

**Optimization Recommendations**:
1. Stream LLM tokens and start TTS on first sentence
2. Use `StreamingResponseHandler.parallel_tts_and_next_llm()`
3. Pre-generate TTS for predicted next responses
4. Implement sentence-level TTS pipelining

---

### BOTTLENECK #4: Database Commits in Critical Path (MEDIUM IMPACT)

**File**: `backend/app/agents/voice_agent.py`
**Lines**: 704-711, 1298

**Current Implementation**:
```python
call.full_transcript = (existing + "\n" + chunk).strip() if existing else chunk
self.db.commit()
```

**Issue**:
- Synchronous DB commits on every transcript append
- Multiple commits per turn (transcript + call updates)
- No batching of database writes

**Estimated Latency**: 20-100ms per commit (3-4 commits per turn)
**Impact**: MEDIUM

**Optimization Recommendations**:
1. Batch commits at end of turn only
2. Use async database driver (asyncpg for PostgreSQL, aiomysql for MySQL)
3. Queue transcript updates for background processing
4. Use `db.commit()` only once per turn

---

### BOTTLENECK #5: Prompt Building with Full Transcript (MEDIUM IMPACT)

**File**: `backend/app/agents/voice_agent.py`
**Lines**: 849-892

**Current Implementation**:
```python
def _transcript_tail(self, call: Call, limit: int = 800) -> str:
    return (call.full_transcript or "")[-limit:]
```

**Issue**:
- Includes 800 chars of transcript in every prompt
- String slicing on potentially large transcript
- Template formatting with many parameters

**Estimated Latency**: 5-20ms
**Impact**: LOW-MEDIUM

**Optimization Recommendations**:
1. Cache formatted prompts for repeated states
2. Use rolling window instead of tail slice
3. Pre-compute transcript context on append
4. Consider smaller context (400-500 chars)

---

### BOTTLENECK #6: Response Cache Key Generation (LOW IMPACT)

**File**: `backend/app/utils/response_cache.py`
**Lines**: 26-30

**Current Implementation**:
```python
def _make_key(self, state_id: int, lead_id: int, user_input: str) -> str:
    input_hash = hashlib.md5(user_input.lower().strip().encode()).hexdigest()[:8]
    return f"{state_id}_{lead_id}_{input_hash}"
```

**Issue**:
- MD5 hashing on every cache lookup
- String operations (lower, strip, encode) add overhead

**Estimated Latency**: 0.1-1ms
**Impact**: LOW

**Optimization Recommendations**:
1. Use faster hash (xxhash, murmurhash)
2. Pre-compute hash on cache set
3. Use LRU cache with object identity keys

---

### BOTTLENECK #7: Quality Tracker Analysis (LOW IMPACT)

**File**: `backend/app/utils/quality_tracker.py`
**Lines**: 55-120

**Current Implementation**:
```python
quality_metrics = quality_tracker.analyze_response(
    response_text=reply_clean,
    response_type=response_type,
    user_input=user_input,
)
```

**Issue**:
- Runs on every response in critical path
- Multiple regex operations and string searches
- Not essential for voice latency

**Estimated Latency**: 1-5ms
**Impact**: LOW

**Optimization Recommendations**:
1. Move to background task
2. Sample-based tracking (every 10th response)
3. Async quality analysis after turn completes

---

### BOTTLENECK #8: WebSocket Broadcast in Turn Path (LOW IMPACT)

**File**: `backend/app/api/calls.py`
**Lines**: 490-495, 506-511

**Current Implementation**:
```python
await manager.broadcast({
    "type": "call_transcript_update",
    ...
})
```

**Issue**:
- Two broadcasts per turn (user speech + agent response)
- Awaited in critical path
- Can block if clients are slow

**Estimated Latency**: 1-10ms per broadcast
**Impact**: LOW

**Optimization Recommendations**:
1. Fire-and-forget broadcasts (don't await)
2. Use `asyncio.create_task()` for non-blocking
3. Batch updates if multiple in quick succession

---

### BOTTLENECK #9: Intent Detection Functions (LOW IMPACT)

**File**: `backend/app/agents/voice_agent.py`
**Lines**: 726-809

**Current Implementation**:
```python
def _detect_no_time(self, user_text: str) -> bool:
    t = (user_text or "").lower()
    return any(p in t for p in ["no time", "can't talk", ...])
```

**Issue**:
- Multiple detection functions called sequentially
- Each does string operations (lower, strip)
- Called 10+ times per turn

**Estimated Latency**: 0.5-2ms total
**Impact**: LOW

**Optimization Recommendations**:
1. Single-pass intent classification
2. Pre-lowercase input once
3. Use trie or regex union for pattern matching
4. Consider ML-based intent classifier

---

### BOTTLENECK #10: TTS Cache File I/O (MEDIUM IMPACT)

**File**: `backend/app/services/openai_service.py`
**Lines**: 168-175, 206-207

**Current Implementation**:
```python
if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
    return os.path.abspath(filepath)
# ...
with open(filepath, "wb") as f:
    f.write(audio_bytes)
```

**Issue**:
- Synchronous file I/O for cache check
- File write blocks on large audio files
- No async file operations

**Estimated Latency**: 5-50ms
**Impact**: MEDIUM (on cache miss)

**Optimization Recommendations**:
1. Use `aiofiles` for async file I/O
2. Keep LRU cache of recent audio in memory
3. Use tmpfs/ramdisk for TTS cache directory
4. Async file write in background

---

### BOTTLENECK #11: Twilio STT Latency (EXTERNAL, HIGH IMPACT)

**File**: N/A (Twilio's built-in)

**Current Implementation**:
- Using Twilio's `<Gather input="speech">` with `speech_timeout="auto"`

**Issue**:
- Twilio's STT has inherent latency (500-1500ms)
- `speech_timeout="auto"` can add delays
- No access to partial transcripts

**Estimated Latency**: 500-1,500ms (uncontrollable)
**Impact**: HIGH (but external)

**Optimization Recommendations**:
1. Use shorter `timeout=4` instead of 6
2. Consider `barge_in=True` for faster interrupts (already enabled)
3. Evaluate Twilio Media Streams for real-time audio access
4. Consider AssemblyAI or Deepgram for faster STT

---

### BOTTLENECK #12: Model Cold Start (HIGH IMPACT, INTERMITTENT)

**File**: `backend/app/utils/model_warmup.py`
**Lines**: 1-159

**Current Implementation**:
```python
# Warmup exists but may not run on every startup
async def warmup_llm(openai_service) -> bool:
    prompt = "Respond with 'Ready' in one word only."
```

**Issue**:
- First request after cold start takes 2-3x longer
- HTTP connection pool not pre-warmed
- TTS cache empty on fresh start

**Estimated Latency**: +1,000-2,000ms (first request only)
**Impact**: HIGH (intermittent)

**Optimization Recommendations**:
1. Ensure warmup runs in `startup_event`
2. Add warmup to health check endpoint
3. Use Lambda/Function provisioned concurrency if serverless
4. Keep-alive requests during idle periods

---

### BOTTLENECK #13: Response Postprocessing (LOW IMPACT)

**File**: `backend/app/agents/voice_agent.py`
**Lines**: 894-917

**Current Implementation**:
```python
def _postprocess_agent_text(self, lead: Lead, text: str) -> str:
    # Multiple regex operations
    t = re.sub(r"(?im)^AGENT\s*:\s*", "", t).strip()
    parts = re.split(r"(?<=[.!?])\s+", t)
    # ...
```

**Issue**:
- Multiple regex operations
- Sentence splitting and joining
- Word counting and truncation

**Estimated Latency**: 1-3ms
**Impact**: LOW

**Optimization Recommendations**:
1. Compile regex patterns once at class level
2. Simplify postprocessing
3. Have LLM output cleaner responses

---

### BOTTLENECK #14: State Routing Logic (LOW IMPACT)

**File**: `backend/app/agents/voice_agent.py`
**Lines**: 1026-1106

**Current Implementation**:
```python
def _route_state_before_reply(self, cur: SalesState, user_text: str, state: Dict[str, Any]) -> SalesState:
    # Large if-elif chain with detection calls
```

**Issue**:
- Sequential state checking
- Multiple detection function calls per state
- Complex conditional logic

**Estimated Latency**: 1-3ms
**Impact**: LOW

**Optimization Recommendations**:
1. Use state machine pattern with transitions
2. Cache detection results
3. Simplify state transitions

---

### BOTTLENECK #15: Transcript Upsert (MEDIUM IMPACT)

**File**: `backend/app/api/calls.py`
**Lines**: 110-132, 504

**Current Implementation**:
```python
_upsert_transcript(db, call)  # Called in critical path
```

**Issue**:
- Separate Transcript table upsert
- Query + conditional insert/update
- In critical turn path

**Estimated Latency**: 10-50ms
**Impact**: MEDIUM

**Optimization Recommendations**:
1. Defer to background task
2. Use `INSERT ... ON DUPLICATE KEY UPDATE`
3. Remove if Call.full_transcript is sufficient
4. Batch at end of call only

---

## Latency Budget Breakdown

### Current State (Estimated)

| Component | Min (ms) | Max (ms) | Avg (ms) |
|-----------|----------|----------|----------|
| Twilio STT | 500 | 1,500 | 900 |
| Intent Detection | 1 | 5 | 2 |
| State Routing | 1 | 3 | 2 |
| Prompt Building | 5 | 20 | 10 |
| Quick Response Check | 0 | 1 | 0.5 |
| Cache Lookup | 0 | 2 | 1 |
| **LLM API Call** | **1,500** | **3,000** | **2,000** |
| Postprocessing | 1 | 3 | 2 |
| **TTS Generation** | **800** | **2,000** | **1,200** |
| TTS Cache I/O | 5 | 50 | 20 |
| DB Commits | 40 | 200 | 80 |
| WebSocket Broadcast | 2 | 20 | 5 |
| Quality Tracking | 1 | 5 | 2 |
| **Total** | **2,856** | **6,809** | **4,224** |

### Target State (After Optimization)

| Component | Target (ms) | Optimization |
|-----------|-------------|--------------|
| Twilio STT | 900 | Use Media Streams (future) |
| Intent Detection | 1 | Single-pass classifier |
| State Routing | 1 | State machine pattern |
| Prompt Building | 5 | Cached templates |
| Quick Response | 0.5 | (keep as is) |
| Cache Lookup | 0.5 | xxhash |
| **LLM Streaming** | **500** | Stream first tokens |
| Postprocessing | 1 | Compiled regex |
| **TTS Streaming** | **200** | Stream to Twilio |
| TTS Cache I/O | 5 | Memory cache |
| DB Commits | 10 | Async + batch |
| WebSocket | 1 | Fire-and-forget |
| Quality Track | 0 | Background |
| **Total** | **~1,125** | **73% reduction** |

---

## Data Flow Diagram: Current vs Proposed

### Current Flow (Sequential)
```
User Speech → [Twilio STT 900ms] → Server
     ↓
[Intent Detection 2ms]
     ↓
[State Routing 2ms]
     ↓
[Prompt Build 10ms]
     ↓
[LLM API 2000ms] ←── BLOCKING
     ↓
[Postprocess 2ms]
     ↓
[TTS Generate 1200ms] ←── BLOCKING
     ↓
[TwiML Response]
     ↓
User hears response

TOTAL: ~4,200ms
```

### Proposed Flow (Streaming + Parallel)
```
User Speech → [Twilio STT 900ms] → Server
     ↓
[Intent + Route + Prompt 15ms total]
     ↓
[LLM Stream Start] ──→ [First tokens 200ms]
     ↓                        ↓
[Continue LLM]          [TTS Stream Start]
     ↓                        ↓
[More tokens]           [Audio chunks → Twilio]
     ↓                        ↓
[LLM Complete]          [User hears audio]

User hears first audio: ~1,100ms
Full response plays: ~2,500ms (but user hears early)

PERCEIVED LATENCY: ~1,100ms (74% improvement)
```

---

## Priority Matrix

| Bottleneck | Impact | Effort | Priority |
|------------|--------|--------|----------|
| #3 Sequential Pipeline | HIGH | HIGH | P0 |
| #1 LLM No Streaming | HIGH | MEDIUM | P0 |
| #2 TTS No Streaming | HIGH | HIGH | P1 |
| #12 Cold Start | HIGH | LOW | P1 |
| #4 DB Commits | MEDIUM | MEDIUM | P2 |
| #10 TTS Cache I/O | MEDIUM | LOW | P2 |
| #15 Transcript Upsert | MEDIUM | LOW | P2 |
| #5 Prompt Building | MEDIUM | LOW | P3 |
| #11 Twilio STT | HIGH | VERY HIGH | P3 (external) |
| Others | LOW | LOW | P4 |

---

## Baseline Performance Metrics

Based on code analysis, estimated current metrics:

- **Time-to-First-Byte (TTFB)**: 2,500-4,500ms
- **LLM Response Time**: 1,500-3,000ms
- **TTS Generation Time**: 800-2,000ms
- **Quick Response Rate**: ~15% of turns (STATE_0, 1, 12)
- **Cache Hit Rate**: Unknown (depends on conversation patterns)
- **Cold Start Penalty**: +1,000-2,000ms

---

## Recommendations Summary

### Immediate (P0/P1)
1. Implement LLM token streaming
2. Start TTS generation on first sentence
3. Ensure model warmup runs on startup
4. Use fire-and-forget for WebSocket broadcasts

### Short-term (P2)
1. Batch database commits
2. Use async file I/O for TTS cache
3. Move transcript upsert to background
4. Memory cache for recent TTS audio

### Medium-term (P3)
1. Consider Twilio Media Streams for real-time audio
2. Implement sentence-level TTS pipelining
3. Evaluate faster STT providers
4. ML-based intent classification

---

## Next Steps

1. Implement P0 optimizations first
2. Measure actual latency with instrumentation
3. A/B test optimized vs current flow
4. Iterate based on real metrics
