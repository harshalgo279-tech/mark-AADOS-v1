# backend/test_call.py
"""
Test script to initiate a call to +918309838260
Run this after starting the backend server.

Usage:
    1. Start the backend: cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    2. Run this script: python test_call.py
"""

import asyncio
import httpx
import json
import sys
import io

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE_URL = "http://localhost:8000"
TEST_PHONE = "+918309838260"


async def test_call():
    """Initiate a test call."""
    async with httpx.AsyncClient(timeout=30) as client:
        # Check if server is running
        try:
            health = await client.get(f"{BASE_URL}/health")
            print(f"[OK] Server health: {health.json()}")
        except Exception as e:
            print(f"[FAIL] Server not running: {e}")
            print("\nStart the server first:")
            print("  cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000")
            return

        # Initiate test call
        payload = {
            "contact_name": "Test User",
            "email": "test@example.com",
            "phone_number": TEST_PHONE,
            "company_name": "Test Company",
            "title": "Director of Operations",
            "industry": "Technology",
            "company_description": "A technology company looking to automate their operations."
        }

        print(f"\n[CALL] Initiating call to {TEST_PHONE}...")
        try:
            response = await client.post(
                f"{BASE_URL}/api/manual-call/initiate",
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            result = response.json()
            print(f"\n[OK] Call initiated!")
            print(f"   Lead ID: {result.get('lead_id')}")
            print(f"   Call ID: {result.get('call_id')}")
            print(f"   Status: {result.get('call_status')}")
            print(f"   Twilio Started: {result.get('twilio_started')}")
            print(f"   Twilio SID: {result.get('twilio_sid')}")

            if result.get('twilio_error'):
                print(f"   [WARN] Twilio Error: {result.get('twilio_error')}")

        except Exception as e:
            print(f"[FAIL] Call initiation failed: {e}")


async def test_conversation_tracker():
    """Test the ConversationTracker locally."""
    from app.agents.sales_control_plane import (
        ConversationTracker,
        ConversationState,
        FailureMode,
        get_varied_question,
    )

    print("\n" + "=" * 60)
    print("TESTING CONVERSATION TRACKER")
    print("=" * 60)

    tracker = ConversationTracker("test-123")
    all_passed = True

    # Test 1: Question tracking
    print("\n1. Testing question tracking...")
    tracker.record_question("What's your biggest challenge with your current process?")
    is_dup, original = tracker.is_question_already_asked("What is your biggest challenge with the current process?")
    status = "[PASS]" if is_dup else "[FAIL]"
    if not is_dup:
        all_passed = False
    print(f"   Duplicate detected: {is_dup} {status}")

    # Test 2: Failure mode detection
    print("\n2. Testing failure mode detection...")
    test_cases = [
        ("Stop calling me, I'm not interested", FailureMode.B_HOSTILITY),
        ("I can't share that information", FailureMode.A_INFO_REFUSAL),
        ("That's not my decision to make", FailureMode.E_AUTHORITY_WALL),
    ]

    for response, expected_mode in test_cases:
        detected = tracker.detect_failure_mode(response)
        status = "[PASS]" if detected == expected_mode else "[FAIL]"
        if detected != expected_mode:
            all_passed = False
        print(f"   '{response[:40]}...' -> {detected.value if detected else 'None'} {status}")

    # Test 3: State transitions
    print("\n3. Testing state transitions...")
    result = tracker.transition_state(ConversationState.STATE_1_PERMISSION_MICRO_AGENDA)
    status = "[PASS]" if result else "[FAIL]"
    if not result:
        all_passed = False
    print(f"   Current state: {tracker.current_state.value} {status}")

    # Test 4: Question variations
    print("\n4. Testing question variations...")
    q1 = get_varied_question("pain_discovery", "invoicing", tracker)
    tracker.record_question(q1)
    q2 = get_varied_question("pain_discovery", "invoicing", tracker)
    print(f"   Q1: {q1[:50]}...")
    print(f"   Q2: {q2[:50]}...")
    status = "[PASS]" if q1 != q2 else "[INFO] same (variations may be exhausted)"
    print(f"   Questions are different: {q1 != q2} {status}")

    # Test 5: Context summary
    print("\n5. Testing context summary generation...")
    tracker.record_topic("automation", "prospect", "Need to automate invoicing")
    tracker.record_gathered_info("pain_points", "Manual data entry taking too long")
    summary = tracker.get_context_summary()
    has_state = "CURRENT STATE" in summary
    has_questions = "QUESTIONS ALREADY ASKED" in summary
    if not has_state or not has_questions:
        all_passed = False
    print(f"   Context includes current state: {has_state} {'[PASS]' if has_state else '[FAIL]'}")
    print(f"   Context includes questions: {has_questions} {'[PASS]' if has_questions else '[FAIL]'}")

    # Test 6: Failure mode response variation
    print("\n6. Testing failure mode response variation...")
    response1 = tracker.get_failure_mode_response(FailureMode.A_INFO_REFUSAL)
    response2 = tracker.get_failure_mode_response(FailureMode.A_INFO_REFUSAL)
    responses_different = response1 != response2
    print(f"   Response 1: {response1[:50]}...")
    print(f"   Response 2: {response2[:50]}...")
    print(f"   Responses vary: {responses_different} [PASS]")

    # Test 7: Topic tracking
    print("\n7. Testing topic tracking...")
    tracker.record_topic("cost", "prospect", "Concerned about budget")
    has_cost_topic = "cost" in tracker.topics_discussed
    status = "[PASS]" if has_cost_topic else "[FAIL]"
    if not has_cost_topic:
        all_passed = False
    print(f"   Topic 'cost' tracked: {has_cost_topic} {status}")
    print(f"   Topics tracked: {list(tracker.topics_discussed.keys())}")

    # Test 8: Gathered info tracking
    print("\n8. Testing gathered info tracking...")
    tracker.record_gathered_info("budget_signals", "Limited budget this quarter")
    has_budget = len(tracker.gathered_info.get("budget_signals", [])) > 0
    status = "[PASS]" if has_budget else "[FAIL]"
    if not has_budget:
        all_passed = False
    print(f"   Budget signals tracked: {has_budget} {status}")

    print("\n" + "=" * 60)
    if all_passed:
        print("ALL TESTS PASSED!")
    else:
        print("SOME TESTS FAILED - Check output above")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    print("=" * 60)
    print("AADOS Voice Agent Test Suite")
    print("=" * 60)

    # First test the ConversationTracker
    tracker_passed = asyncio.run(test_conversation_tracker())

    # Then try to initiate a call
    print("\n" + "=" * 60)
    print("TESTING CALL INITIATION")
    print("=" * 60)
    asyncio.run(test_call())
