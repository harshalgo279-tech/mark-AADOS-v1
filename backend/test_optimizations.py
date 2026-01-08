#!/usr/bin/env python3
"""
End-to-end test for all latency optimizations implemented in Phase 2.
Run with: python test_optimizations.py
"""

import asyncio
import sys
import time
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.utils.logger import logger

# Test results tracking
results = []

def log_result(test_name: str, passed: bool, details: str = "", latency_ms: float = None):
    status = "PASS" if passed else "FAIL"
    latency_str = f" ({latency_ms:.2f}ms)" if latency_ms else ""
    print(f"[{status}] {test_name}{latency_str}: {details}")
    results.append({"test": test_name, "passed": passed, "details": details, "latency_ms": latency_ms})


async def test_1_llm_streaming():
    """Test 1: LLM Streaming with AsyncOpenAI client"""
    print("\n" + "="*60)
    print("TEST 1: LLM Streaming")
    print("="*60)

    try:
        from app.services.openai_service import OpenAIService

        service = OpenAIService()

        # Check if async client is available
        async_client = OpenAIService.get_async_client()
        if async_client is None:
            log_result("LLM Streaming - AsyncClient", False, "AsyncOpenAI client not available (check API key)")
            return

        log_result("LLM Streaming - AsyncClient", True, "AsyncOpenAI client initialized")

        # Test streaming completion
        start = time.time()
        first_token_time = None

        async def on_first_sentence(sentence):
            nonlocal first_token_time
            first_token_time = (time.time() - start) * 1000

        response = await service.generate_completion_streaming(
            prompt="Say hello in one sentence.",
            temperature=0.5,
            max_tokens=50,
            timeout_s=30.0,
            on_first_sentence=on_first_sentence
        )

        total_time = (time.time() - start) * 1000

        if response:
            log_result("LLM Streaming - Response", True, f"Got response: '{response[:50]}...'", total_time)
        else:
            log_result("LLM Streaming - Response", False, "Empty response")

    except Exception as e:
        log_result("LLM Streaming", False, f"Error: {e}")


async def test_2_tts_memory_cache():
    """Test 2: TTS Memory Cache"""
    print("\n" + "="*60)
    print("TEST 2: TTS Memory Cache")
    print("="*60)

    try:
        from app.services.openai_service import OpenAIService, TTSMemoryCache

        # Test TTSMemoryCache class
        cache = TTSMemoryCache(max_size=5)

        # Test set and get
        cache.set("key1", b"audio_data_1")
        cache.set("key2", b"audio_data_2")

        result1 = cache.get("key1")
        result2 = cache.get("key2")
        result3 = cache.get("nonexistent")

        if result1 == b"audio_data_1" and result2 == b"audio_data_2" and result3 is None:
            log_result("TTS Memory Cache - Basic", True, "Set/Get working correctly")
        else:
            log_result("TTS Memory Cache - Basic", False, "Set/Get not working")

        # Test LRU eviction
        for i in range(10):
            cache.set(f"key_{i}", f"data_{i}".encode())

        # First keys should be evicted
        evicted = cache.get("key1") is None
        recent = cache.get("key_9") is not None

        if evicted and recent:
            log_result("TTS Memory Cache - LRU", True, "LRU eviction working")
        else:
            log_result("TTS Memory Cache - LRU", False, f"LRU not working: evicted={evicted}, recent={recent}")

        # Test class-level cache
        service_cache = OpenAIService.get_tts_memory_cache()
        if service_cache is not None:
            log_result("TTS Memory Cache - Service", True, "Class-level cache available")
        else:
            log_result("TTS Memory Cache - Service", False, "Class-level cache not available")

    except Exception as e:
        log_result("TTS Memory Cache", False, f"Error: {e}")


async def test_3_async_file_io():
    """Test 3: Async File I/O"""
    print("\n" + "="*60)
    print("TEST 3: Async File I/O")
    print("="*60)

    try:
        from app.services.openai_service import OpenAIService, AIOFILES_AVAILABLE

        if AIOFILES_AVAILABLE:
            log_result("Async File I/O - aiofiles", True, "aiofiles is available")
        else:
            log_result("Async File I/O - aiofiles", False, "aiofiles not installed - using fallback")

        # Test async file operations
        service = OpenAIService()
        test_file = "test_async_io.tmp"
        test_data = b"test data for async io"

        # Write
        start = time.time()
        await service._write_file_async(test_file, test_data)
        write_time = (time.time() - start) * 1000

        # Check exists
        exists = await service._file_exists_async(test_file)

        # Read
        start = time.time()
        read_data = await service._read_file_async(test_file)
        read_time = (time.time() - start) * 1000

        # Cleanup
        if os.path.exists(test_file):
            os.remove(test_file)

        if exists and read_data == test_data:
            log_result("Async File I/O - Operations", True, f"Write: {write_time:.2f}ms, Read: {read_time:.2f}ms")
        else:
            log_result("Async File I/O - Operations", False, f"exists={exists}, data_match={read_data == test_data}")

    except Exception as e:
        log_result("Async File I/O", False, f"Error: {e}")


async def test_4_websocket_fire_and_forget():
    """Test 4: Fire-and-Forget WebSocket Broadcasts"""
    print("\n" + "="*60)
    print("TEST 4: WebSocket Fire-and-Forget")
    print("="*60)

    try:
        from app.api.websocket import ConnectionManager

        manager = ConnectionManager()

        # Check method exists
        if hasattr(manager, 'broadcast_fire_and_forget'):
            log_result("WebSocket - Method", True, "broadcast_fire_and_forget method exists")
        else:
            log_result("WebSocket - Method", False, "broadcast_fire_and_forget method missing")
            return

        # Test that it doesn't block (no connections, should return immediately)
        start = time.time()
        manager.broadcast_fire_and_forget({"type": "test", "data": "test_message"})
        elapsed = (time.time() - start) * 1000

        if elapsed < 10:  # Should be nearly instant with no connections
            log_result("WebSocket - Non-blocking", True, f"Returned in {elapsed:.2f}ms")
        else:
            log_result("WebSocket - Non-blocking", False, f"Took {elapsed:.2f}ms - may be blocking")

    except Exception as e:
        log_result("WebSocket Fire-and-Forget", False, f"Error: {e}")


async def test_5_database_batching():
    """Test 5: Database Commit Batching"""
    print("\n" + "="*60)
    print("TEST 5: Database Commit Batching")
    print("="*60)

    try:
        from app.agents.voice_agent import VoiceAgent
        import inspect

        # Check if append_to_call_transcript has commit parameter
        sig = inspect.signature(VoiceAgent.append_to_call_transcript)
        params = list(sig.parameters.keys())

        if 'commit' in params:
            log_result("DB Batching - Parameter", True, "commit parameter exists in append_to_call_transcript")
        else:
            log_result("DB Batching - Parameter", False, f"commit parameter missing. Params: {params}")

    except Exception as e:
        log_result("Database Batching", False, f"Error: {e}")


async def test_6_precompiled_regex():
    """Test 6: Pre-compiled Regex Patterns"""
    print("\n" + "="*60)
    print("TEST 6: Pre-compiled Regex Patterns")
    print("="*60)

    try:
        from app.agents.voice_agent import VoiceAgent
        import re

        # Check class-level regex patterns
        patterns = [
            '_RE_SPEAKER_LABEL_START',
            '_RE_SPEAKER_LABEL_NEWLINE',
            '_RE_AGENT_PREFIX',
            '_RE_DOUBLE_AGENT',
            '_RE_DOUBLE_LEAD',
            '_RE_WHITESPACE',
            '_RE_SENTENCE_SPLIT',
        ]

        found = []
        missing = []
        for pattern in patterns:
            if hasattr(VoiceAgent, pattern):
                attr = getattr(VoiceAgent, pattern)
                if isinstance(attr, re.Pattern):
                    found.append(pattern)
                else:
                    missing.append(f"{pattern} (not compiled)")
            else:
                missing.append(pattern)

        if len(found) == len(patterns):
            log_result("Pre-compiled Regex", True, f"All {len(found)} patterns compiled")
        else:
            log_result("Pre-compiled Regex", False, f"Found: {len(found)}, Missing: {missing}")

    except Exception as e:
        log_result("Pre-compiled Regex", False, f"Error: {e}")


async def test_7_single_pass_intent_detection():
    """Test 7: Single-Pass Intent Detection"""
    print("\n" + "="*60)
    print("TEST 7: Single-Pass Intent Detection")
    print("="*60)

    try:
        from app.agents.voice_agent import VoiceAgent
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            agent = VoiceAgent(db)

            # Check method exists
            if not hasattr(agent, '_detect_all_intents'):
                log_result("Intent Detection - Method", False, "_detect_all_intents method missing")
                return

            log_result("Intent Detection - Method", True, "_detect_all_intents method exists")

            # Test detection
            test_cases = [
                ("I'm busy right now", {"no_time": True}),
                ("not interested thanks", {"not_interested": True}),
                ("yes sure go ahead", {"permission_granted": True}),
                ("can't hear you", {"tech_issue": True}),
                ("who is this?", {"who_is_this": True}),
            ]

            passed = 0
            for text, expected in test_cases:
                start = time.time()
                result = agent._detect_all_intents(text)
                elapsed = (time.time() - start) * 1000

                # Check expected keys are True
                all_match = True
                for key, val in expected.items():
                    if result.get(key) != val:
                        all_match = False
                        break

                if all_match:
                    passed += 1

            if passed == len(test_cases):
                log_result("Intent Detection - Accuracy", True, f"All {passed} test cases passed")
            else:
                log_result("Intent Detection - Accuracy", False, f"{passed}/{len(test_cases)} test cases passed")

            # Benchmark speed
            start = time.time()
            for _ in range(100):
                agent._detect_all_intents("I'm not interested in your product right now, I'm busy")
            elapsed = (time.time() - start) * 1000
            avg = elapsed / 100

            log_result("Intent Detection - Speed", True, f"Average: {avg:.3f}ms per call", avg)

        finally:
            db.close()

    except Exception as e:
        log_result("Intent Detection", False, f"Error: {e}")


async def test_8_cache_key_blake2b():
    """Test 8: BLAKE2b Cache Key Generation"""
    print("\n" + "="*60)
    print("TEST 8: BLAKE2b Cache Key Generation")
    print("="*60)

    try:
        from app.utils.response_cache import ResponseCache
        import hashlib

        cache = ResponseCache()

        # Test key generation
        key1 = cache._make_key(1, 100, "hello world")
        key2 = cache._make_key(1, 100, "hello world")
        key3 = cache._make_key(1, 100, "different input")

        if key1 == key2 and key1 != key3:
            log_result("Cache Key - Consistency", True, f"Keys: {key1}, {key3}")
        else:
            log_result("Cache Key - Consistency", False, f"Inconsistent keys")

        # Benchmark speed
        import time

        # BLAKE2b (current)
        start = time.time()
        for _ in range(10000):
            cache._make_key(1, 100, "test input for benchmarking")
        blake2_time = (time.time() - start) * 1000

        # MD5 comparison
        start = time.time()
        for _ in range(10000):
            hashlib.md5("test input for benchmarking".lower().strip().encode()).hexdigest()[:8]
        md5_time = (time.time() - start) * 1000

        speedup = md5_time / blake2_time if blake2_time > 0 else 0
        log_result("Cache Key - Speed", True, f"BLAKE2b: {blake2_time:.2f}ms, MD5: {md5_time:.2f}ms, Speedup: {speedup:.1f}x")

    except Exception as e:
        log_result("Cache Key", False, f"Error: {e}")


async def test_9_http_client_pool():
    """Test 9: HTTP Client Connection Pooling"""
    print("\n" + "="*60)
    print("TEST 9: HTTP Client Connection Pooling")
    print("="*60)

    try:
        from app.services.openai_service import OpenAIService

        # Get client (creates if not exists)
        client1 = OpenAIService.get_http_client()
        client2 = OpenAIService.get_http_client()

        # Should be same instance (connection pooling)
        if client1 is client2:
            log_result("HTTP Pool - Singleton", True, "Same client instance returned")
        else:
            log_result("HTTP Pool - Singleton", False, "Different client instances")

        # Check client is ready
        if client1 is not None and not client1.is_closed:
            log_result("HTTP Pool - Ready", True, "Client is ready for requests")
        else:
            log_result("HTTP Pool - Ready", False, "Client not ready")

    except Exception as e:
        log_result("HTTP Pool", False, f"Error: {e}")


async def test_10_intent_frozensets():
    """Test 10: Intent Pattern Frozensets"""
    print("\n" + "="*60)
    print("TEST 10: Intent Pattern Frozensets")
    print("="*60)

    try:
        from app.agents.voice_agent import VoiceAgent

        frozenset_attrs = [
            '_INTENT_NO_TIME',
            '_INTENT_JUST_TELL',
            '_INTENT_HOSTILE',
            '_INTENT_NOT_INTERESTED',
            '_INTENT_TECH_ISSUE',
            '_INTENT_WHO_IS_THIS',
            '_INTENT_PERMISSION_YES',
            '_INTENT_PERMISSION_NO',
            '_INTENT_GUARDED',
            '_INTENT_CONFIRM_YES',
            '_INTENT_RESONANCE',
            '_INTENT_HESITATION',
            '_INTENT_SCHEDULE',
        ]

        found = []
        missing = []
        for attr in frozenset_attrs:
            if hasattr(VoiceAgent, attr):
                val = getattr(VoiceAgent, attr)
                if isinstance(val, frozenset):
                    found.append(attr)
                else:
                    missing.append(f"{attr} (type: {type(val).__name__})")
            else:
                missing.append(attr)

        if len(found) == len(frozenset_attrs):
            log_result("Intent Frozensets", True, f"All {len(found)} frozensets defined")
        else:
            log_result("Intent Frozensets", False, f"Found: {len(found)}, Missing: {missing[:3]}...")

    except Exception as e:
        log_result("Intent Frozensets", False, f"Error: {e}")


async def main():
    print("="*60)
    print("AADOS VOICE AGENT - LATENCY OPTIMIZATION TESTS")
    print("="*60)
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Run all tests
    await test_1_llm_streaming()
    await test_2_tts_memory_cache()
    await test_3_async_file_io()
    await test_4_websocket_fire_and_forget()
    await test_5_database_batching()
    await test_6_precompiled_regex()
    await test_7_single_pass_intent_detection()
    await test_8_cache_key_blake2b()
    await test_9_http_client_pool()
    await test_10_intent_frozensets()

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = sum(1 for r in results if r['passed'])
    failed = sum(1 for r in results if not r['passed'])
    total = len(results)

    print(f"\nTotal: {total} tests")
    print(f"Passed: {passed} ({100*passed/total:.0f}%)")
    print(f"Failed: {failed}")

    if failed > 0:
        print("\nFailed tests:")
        for r in results:
            if not r['passed']:
                print(f"  - {r['test']}: {r['details']}")

    print("\n" + "="*60)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
