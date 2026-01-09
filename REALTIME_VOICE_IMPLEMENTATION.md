# OpenAI Realtime Voice Implementation

This document describes the implementation of OpenAI's Realtime Voice API with WebRTC for low-latency voice interactions.

## Overview

The Realtime Voice functionality provides direct browser-to-OpenAI WebRTC connections for real-time voice chat with minimal latency. This implementation uses:

- **WebRTC** for peer-to-peer audio streaming
- **OpenAI Realtime API** (`gpt-4o-realtime-preview-2024-12-17`)
- **Real-time transcription** with progressive delta updates
- **Echo cancellation, noise suppression, and auto gain control**

## Architecture

### Frontend Components

1. **useWebRTC Hook** (`frontend/src/hooks/useWebRTC.js`)
   - Manages WebRTC peer connection lifecycle
   - Handles audio capture with optimized settings
   - Processes real-time transcription events
   - Provides session control methods

2. **RealtimeVoiceChat Component** (`frontend/src/components/RealtimeVoiceChat.jsx`)
   - User interface for voice chat
   - Real-time transcript display (user and agent)
   - Connection controls and status indicators
   - Error handling and feedback

### Backend Endpoint

**Endpoint**: `POST /api/realtime/session`
**File**: `backend/app/api/realtime.py`

**Purpose**: Generate ephemeral API keys for secure client-side OpenAI connections

**Flow**:
1. Frontend requests an ephemeral key from the backend
2. Backend uses the main OpenAI API key to create an ephemeral session
3. Backend returns the ephemeral key (expires in ~60 seconds)
4. Frontend uses the ephemeral key to establish a WebRTC connection directly to OpenAI

This approach ensures the main API key never leaves the server.

## Key Features

### 1. Low-Latency Audio Streaming

Audio is captured with optimized settings for minimal latency:

```javascript
const mediaStream = await navigator.mediaDevices.getUserMedia({
  audio: {
    echoCancellation: true,      // Prevents feedback loops
    noiseSuppression: true,       // Filters background noise
    autoGainControl: true,        // Normalizes volume
    sampleRate: 24000,           // Optimal for speech
    channelCount: 1              // Mono audio
  }
});
```

### 2. Real-Time Transcription

The implementation handles two types of transcription events:

#### Delta Updates (Progressive)
- Event type: `input_audio_transcription.delta`
- Provides incremental transcript updates as the user speaks
- Enables real-time display of words as they're spoken

#### Completion Events (Final)
- Event type: `input_audio_transcription.completed`
- Provides the final, polished transcript when the user stops speaking
- Ensures accuracy after voice activity detection

### 3. WebRTC Data Channel

The WebRTC data channel is used for:
- Sending session configuration
- Receiving transcription events
- Handling agent responses
- Error reporting

### 4. Security

- Main OpenAI API key stored securely on the server
- Ephemeral keys expire automatically (typically 60 seconds)
- Each session gets a unique ephemeral key
- Direct browser-to-OpenAI connection reduces server load

## Usage

### Frontend Usage

```javascript
import useWebRTC from '../hooks/useWebRTC';

const MyComponent = () => {
  const {
    isConnected,
    isRecording,
    userTranscript,
    agentTranscript,
    connect,
    disconnect,
    sendMessage,
    toggleRecording,
    clearTranscripts
  } = useWebRTC({
    model: "gpt-4o-realtime-preview-2024-12-17",
    transcriptionModel: "whisper-1",
    voice: "alloy",
    onTranscriptDelta: (data) => console.log('Delta:', data),
    onTranscriptDone: (data) => console.log('Done:', data),
    onAgentResponse: (audio) => console.log('Response received'),
    onError: (error) => console.error('Error:', error)
  });

  return (
    <div>
      <button onClick={connect}>Start Voice Chat</button>
      <button onClick={disconnect}>End Call</button>
      <button onClick={toggleRecording}>Toggle Mic</button>
      <div>User: {userTranscript}</div>
      <div>Agent: {agentTranscript}</div>
    </div>
  );
};
```

### Backend Configuration

Ensure the `OPENAI_API_KEY` environment variable is set in your backend configuration:

```bash
OPENAI_API_KEY=sk-...
```

## API Reference

### useWebRTC Hook

#### Parameters

- `model` (string): OpenAI model to use (default: "gpt-4o-realtime-preview-2024-12-17")
- `transcriptionModel` (string): Transcription model (default: "whisper-1")
- `voice` (string): Voice for TTS responses (default: "alloy")
- `onTranscriptDelta` (function): Callback for incremental transcript updates
- `onTranscriptDone` (function): Callback for completed transcripts
- `onAgentResponse` (function): Callback for agent audio responses
- `onError` (function): Callback for errors

#### Returns

- `isConnected` (boolean): WebRTC connection status
- `isRecording` (boolean): Microphone recording status
- `userTranscript` (string): Current user transcript
- `agentTranscript` (string): Current agent transcript
- `connect` (function): Establish WebRTC connection
- `disconnect` (function): Close connection and cleanup
- `sendMessage` (function): Send text message to agent
- `toggleRecording` (function): Mute/unmute microphone
- `clearTranscripts` (function): Clear all transcripts

## Troubleshooting

### Common Issues

1. **Microphone Permission Denied**
   - Ensure the browser has permission to access the microphone
   - Check browser security settings
   - HTTPS is required for microphone access (except localhost)

2. **Connection Fails**
   - Verify `OPENAI_API_KEY` is configured correctly
   - Check backend logs for ephemeral key generation errors
   - Ensure OpenAI API has access to Realtime API

3. **No Audio Playback**
   - Check browser audio output settings
   - Verify audio element autoplay is enabled
   - Check for browser autoplay policies

4. **Transcription Not Appearing**
   - Verify data channel is open (check console logs)
   - Ensure session configuration was sent successfully
   - Check for WebRTC connection issues

## Performance Optimizations

1. **Direct WebRTC Connection**: Bypasses server for audio, reducing latency
2. **Optimized Audio Settings**: 24kHz mono with noise suppression
3. **Progressive Transcription**: Delta updates for real-time feedback
4. **Ephemeral Keys**: Lightweight authentication without server overhead
5. **Auto Cleanup**: Proper resource cleanup on disconnect

## Browser Compatibility

- Chrome/Edge: Full support
- Firefox: Full support
- Safari: Full support (may require user gesture for audio)
- Mobile browsers: Limited support (check getUserMedia support)

## Future Enhancements

Potential improvements:
- Voice activity detection visualization
- Conversation history persistence
- Custom agent instructions
- Multi-language support
- Audio recording/playback
- Integration with existing call monitoring

## References

- [OpenAI Realtime API Documentation](https://platform.openai.com/docs/guides/realtime)
- [OpenAI Realtime WebRTC Guide](https://platform.openai.com/docs/guides/realtime-webrtc)
- [WebRTC API Documentation](https://developer.mozilla.org/en-US/docs/Web/API/WebRTC_API)
