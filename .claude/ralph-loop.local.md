---
active: true
iteration: 1
max_iterations: 35
completion_promise: "PHASE2_DONE"
started_at: "2026-01-08T14:43:55Z"
---

Phase 2: Implement latency optimizations across the voice agent codebase.

Based on the bottlenecks identified in Phase 1 (outputs/latency-analysis.md), implement the following optimizations:

HIGH PRIORITY (P0/P1):
1. Implement LLM streaming - Stream tokens from OpenAI instead of waiting for complete response
2. Implement parallel LLM+TTS pipeline - Start TTS generation on first sentence while LLM continues
3. Ensure model warmup runs on startup - Add warmup to FastAPI startup event
4. Use fire-and-forget for WebSocket broadcasts - Don't await broadcasts in critical path

MEDIUM PRIORITY (P2):
5. Batch database commits - Single commit per turn instead of multiple
6. Use async file I/O for TTS cache - Use aiofiles for non-blocking file operations
7. Move transcript upsert to background - Use asyncio.create_task()
8. Add memory cache for recent TTS audio - LRU cache for hot audio files

LOW PRIORITY (P3):
9. Compile regex patterns at class level - Pre-compile all regex in voice_agent.py
10. Single-pass intent detection - Combine all detection into one function
11. Optimize cache key generation - Use faster hashing

Success criteria:
- All P0/P1 optimizations implemented and functional
- All P2 optimizations implemented
- Streaming LLM responses working
- Parallel TTS generation working
- Database commits reduced to 1 per turn
- No breaking changes to existing functionality
- Changes documented in outputs/optimization-changes.md

Output <promise>PHASE2_DONE</promise> when complete.
