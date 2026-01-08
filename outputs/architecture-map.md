# AADOS Voice Agent Architecture Map

## Overview

AADOS (Algonox Automated Dialing and Outbound Sales) is a voice-based AI sales agent built on FastAPI, integrating Twilio for telephony and OpenAI for LLM/TTS capabilities.

---

## System Architecture Diagram

```
                                    AADOS Voice Agent Architecture
+-------------------------------------------------------------------------------------------+
|                                      FRONTEND (React)                                       |
|  +-------------+  +-------------+  +-------------+  +-------------+  +-------------+      |
|  | Dashboard   |  | CallMonitor |  | Transcript  |  | LeadsPanel  |  | PDFViewer   |      |
|  +-------------+  +-------------+  +-------------+  +-------------+  +-------------+      |
|                                          |                                                  |
|                              WebSocket (/ws) + REST API                                    |
+-------------------------------------------------------------------------------------------+
                                           |
                                           v
+-------------------------------------------------------------------------------------------+
|                                   BACKEND (FastAPI)                                         |
|  +------------------+     +------------------+     +------------------+                     |
|  | API Routers      |     | WebSocket Manager|     | Background Tasks |                    |
|  | - calls.py       |     | - websocket.py   |     | - post_call_pipe |                    |
|  | - leads.py       |     |                  |     | - pdf_generation |                    |
|  | - manual_call.py |     |                  |     |                  |                    |
|  +------------------+     +------------------+     +------------------+                     |
|           |                        |                       |                                |
|           v                        v                       v                                |
|  +-----------------------------------------------------------------------------------+     |
|  |                            VOICE AGENT CORE                                       |     |
|  |  +------------------+  +------------------+  +------------------+                 |     |
|  |  | VoiceAgent       |  | State Machine    |  | BANT Scoring     |                 |     |
|  |  | - voice_agent.py |  | (STATE_0..12)    |  | - budget         |                 |     |
|  |  |                  |  | - SPIN-based     |  | - authority      |                 |     |
|  |  +------------------+  +------------------+  +------------------+                 |     |
|  |           |                     |                    |                            |     |
|  |           v                     v                    v                            |     |
|  |  +------------------+  +------------------+  +------------------+                 |     |
|  |  | Prompt Engine    |  | Detection Layer  |  | Response Handler |                 |     |
|  |  | - 13 state temps |  | - intent detect  |  | - postprocess    |                 |     |
|  |  | - context build  |  | - objection det  |  | - TwiML build    |                 |     |
|  |  +------------------+  +------------------+  +------------------+                 |     |
|  +-----------------------------------------------------------------------------------+     |
|                                           |                                                 |
+-------------------------------------------------------------------------------------------+
                                           |
                    +----------------------+----------------------+
                    |                      |                      |
                    v                      v                      v
+------------------+      +------------------+      +------------------+
| LATENCY UTILS    |      | EXTERNAL SERVICES|      | DATA LAYER       |
| +-------------+  |      | +-------------+  |      | +-------------+  |
| |ResponseCache|  |      | |OpenAIService|  |      | | SQLAlchemy  |  |
| |QuickResponse|  |      | | - LLM API   |  |      | | - Call      |  |
| |LatencyTrack |  |      | | - TTS API   |  |      | | - Lead      |  |
| |QualityTrack |  |      | +-------------+  |      | | - Packet    |  |
| |ModelWarmup  |  |      | |TwilioService|  |      | | - Transcript|  |
| |StreamingResp|  |      | | - Call mgmt |  |      | +-------------+  |
| +-------------+  |      | | - Recording |  |      | | MySQL DB    |  |
+------------------+      +------------------+      +------------------+
                                   |
                    +--------------+--------------+
                    |                             |
                    v                             v
            +----------------+            +----------------+
            |   OpenAI API   |            |   Twilio API   |
            | - GPT-4o-mini  |            | - Voice calls  |
            | - TTS (cedar)  |            | - Recording    |
            | - Whisper STT  |            | - Webhooks     |
            +----------------+            +----------------+
```

---

## Core Components

### 1. Voice Agent (`backend/app/agents/voice_agent.py`)
**Lines: 1-1315**

The main voice agent handling call conversations with:
- **State Machine**: 13 states (STATE_0 to STATE_12) for SPIN-based sales flow
- **BANT Scoring**: Budget, Authority, Need, Timeline tracking
- **Detection Layers**: Intent, objection, buying signals, tech issues
- **Prompt Templates**: 13 state-specific prompts with context injection
- **TwiML Generation**: Twilio Voice Response building with `<Gather>` and `<Play>`

Key methods:
- `generate_reply()` - Main response generation (lines 1111-1314)
- `tts_audio_url()` - OpenAI TTS URL generation (lines 551-579)
- `build_turn_twiml()` - TwiML response building (lines 946-978)

### 2. OpenAI Service (`backend/app/services/openai_service.py`)
**Lines: 1-222**

Handles all OpenAI API interactions:
- **LLM Completion**: GPT-4o-mini with configurable timeout (lines 60-103)
- **TTS Generation**: OpenAI Audio API with caching (lines 139-221)
- **STT Transcription**: Whisper model integration (lines 105-126)
- **Connection Pooling**: Shared httpx client for performance (lines 46-58)

### 3. Twilio Service (`backend/app/services/twilio_service.py`)
**Lines: 1-144**

Manages Twilio call orchestration:
- **Outbound Calls**: With webhook configuration (lines 52-119)
- **Recording Download**: With pooled HTTP client (lines 121-137)
- **Status Callbacks**: Optimized event filtering

### 4. Latency Optimization Utilities

| File | Purpose | Key Features |
|------|---------|--------------|
| `response_cache.py` | In-memory LLM response caching | TTL-based, state+lead+input keyed |
| `quick_responses.py` | Deterministic responses for simple states | STATE_0, 1, 12 coverage |
| `latency_tracker.py` | Pipeline stage timing | prompt/llm/tts tracking |
| `streaming_response.py` | Parallel TTS+LLM execution | Reduces TTFB ~83% |
| `model_warmup.py` | Cold-start mitigation | LLM/TTS/HTTP pool warm-up |
| `quality_tracker.py` | Response quality monitoring | Prevents optimization degradation |

### 5. API Endpoints (`backend/app/api/calls.py`)
**Lines: 1-748**

Critical voice endpoints:
- `POST /api/calls/{id}/webhook` - Initial Twilio callback (lines 439-470)
- `POST /api/calls/{id}/webhook/turn` - Conversation turn handler (lines 473-537)
- `POST /api/calls/{id}/webhook/status` - Call status updates (lines 540-578)
- `GET /api/calls/{id}/tts/{filename}` - TTS audio serving (lines 424-436)

---

## Data Flow

### Outbound Call Flow

```
1. User initiates call via API/UI
          |
          v
2. VoiceAgent.initiate_outbound_call()
   - Creates Call record
   - Loads lead context
   - Calls TwilioService.make_call()
          |
          v
3. Twilio connects call, requests TwiML
          |
          v
4. /api/calls/{id}/webhook
   - VoiceAgent builds opener
   - OpenAI TTS generates audio
   - Returns TwiML with <Gather><Play>
          |
          v
5. Prospect speaks, Twilio sends to:
   /api/calls/{id}/webhook/turn
          |
          v
6. Turn Processing (per utterance):
   a. Extract SpeechResult
   b. Append to transcript
   c. VoiceAgent.generate_reply():
      - Try quick_responses (0ms LLM)
      - Check response_cache (0ms LLM)
      - Call OpenAI LLM (1-3s)
   d. Generate TTS audio
   e. Return TwiML with response
          |
          v
7. Loop steps 5-6 until call ends
          |
          v
8. /api/calls/{id}/webhook/status (completed)
   - Trigger post-call pipeline
   - Generate DataPacket, LinkedIn, PDF
```

### Transcript Processing Flow

```
User Speech (Twilio STT)
         |
         v
append_to_call_transcript()
         |
         v
WebSocket broadcast (delta)
         |
         v
_upsert_transcript() to DB
         |
         v
_ensure_call_analysis() (post-call)
         |
         v
OpenAI summarization + sentiment
```

---

## Dependency Map

### Backend (Python)
| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | 0.104.1 | Web framework |
| uvicorn | 0.24.0 | ASGI server |
| openai | 1.3.7 | LLM/TTS API |
| twilio | 8.10.0 | Telephony |
| httpx | 0.25.1 | Async HTTP (connection pooling) |
| sqlalchemy | 2.0.36 | ORM |
| pydantic | 2.9.2 | Data validation |
| python-dotenv | 1.0.0 | Environment |

### Frontend (React)
| Package | Version | Purpose |
|---------|---------|---------|
| react | 18.2.0 | UI framework |
| axios | 1.6.2 | HTTP client |
| recharts | 2.10.3 | Charts |
| lucide-react | 0.263.1 | Icons |
| vite | 5.0.8 | Build tool |

---

## Audio Processing Points

1. **Twilio STT** (incoming): Built-in, no latency control
2. **OpenAI TTS** (outgoing):
   - Endpoint: `https://api.openai.com/v1/audio/speech`
   - Voice: cedar (male)
   - Model: gpt-4o-mini-tts
   - Cache: File-based in `storage/tts/`
3. **Audio Serving**: Static file via `/api/calls/{id}/tts/{filename}`

---

## LLM Integration Points

1. **Response Generation** (`openai_service.py:60-103`)
   - Model: gpt-4o-mini
   - Timeout: 4-6s (state-dependent)
   - Max tokens: 150

2. **Call Analysis** (`calls.py:144-230`)
   - Model: gpt-4o-mini
   - Timeout: 12s
   - Used for post-call summarization

3. **TTS Prompt** (inline text)
   - Model: gpt-4o-mini-tts
   - Timeout: 15-20s

---

## Real-Time Streaming Points (Current)

1. **WebSocket** (`websocket.py`): Broadcasts transcript deltas, call status
2. **No audio streaming**: TTS generates complete audio files
3. **No incremental LLM**: Full completion, not streaming tokens

---

## Configuration

Key settings from `backend/app/config.py`:
- `OPENAI_API_KEY` - OpenAI API access
- `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` - Twilio auth
- `TWILIO_WEBHOOK_URL` - Public webhook base URL
- `DATABASE_URL` - MySQL connection
- `TTS_CACHE_DIR` - TTS audio cache location

---

## File Structure Summary

```
backend/
  app/
    agents/
      voice_agent.py      # Core voice agent (1315 lines)
      email_agent.py      # Email generation
      linkedin_agent.py   # LinkedIn messages
      analyst_agent.py    # Analysis
    api/
      calls.py            # Call webhooks (748 lines)
      websocket.py        # Real-time updates
      leads.py            # Lead management
    services/
      openai_service.py   # OpenAI API (222 lines)
      twilio_service.py   # Twilio API (144 lines)
    utils/
      latency_tracker.py  # Latency measurement
      response_cache.py   # LLM response caching
      quick_responses.py  # Deterministic responses
      streaming_response.py # Parallel operations
      model_warmup.py     # Cold-start mitigation
      quality_tracker.py  # Quality monitoring
    models/
      call.py, lead.py, transcript.py, data_packet.py
    config.py, database.py, main.py
frontend/
  src/
    components/
      Dashboard.jsx, CallMonitor.jsx, TranscriptPage.jsx
    utils/
      websocket.js, api.js
```
