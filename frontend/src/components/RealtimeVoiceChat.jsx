// frontend/src/components/RealtimeVoiceChat.jsx
/**
 * RealtimeVoiceChat Component
 *
 * A real-time voice chat interface using OpenAI's Realtime API with WebRTC.
 * Features:
 * - Low-latency voice interaction
 * - Real-time transcription with progressive rendering
 * - Echo cancellation and noise suppression
 * - Visual feedback for connection status and recording state
 */

import { useState, useCallback } from 'react';
import { Mic, MicOff, Phone, PhoneOff, Trash2 } from 'lucide-react';
import useWebRTC from '../hooks/useWebRTC';

const RealtimeVoiceChat = ({ onClose }) => {
  const [error, setError] = useState(null);
  const [isConnecting, setIsConnecting] = useState(false);

  const {
    isConnected,
    isRecording,
    userTranscript,
    agentTranscript,
    connect,
    disconnect,
    toggleRecording,
    clearTranscripts
  } = useWebRTC({
    model: "gpt-4o-realtime-preview-2024-12-17",
    transcriptionModel: "whisper-1",
    voice: "alloy",
    onTranscriptDelta: (data) => {
      console.log('Transcript delta:', data);
    },
    onTranscriptDone: (data) => {
      console.log('Transcript done:', data);
    },
    onAgentResponse: (audio) => {
      console.log('Agent audio response received');
    },
    onError: (err) => {
      console.error('WebRTC error:', err);
      setError(err.message);
    }
  });

  const handleConnect = useCallback(async () => {
    setIsConnecting(true);
    setError(null);
    try {
      await connect();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsConnecting(false);
    }
  }, [connect]);

  const handleDisconnect = useCallback(() => {
    disconnect();
    setError(null);
  }, [disconnect]);

  const handleClearTranscripts = useCallback(() => {
    clearTranscripts();
  }, [clearTranscripts]);

  return (
    <div style={overlay}>
      <div style={card}>
        {/* Header */}
        <div style={header}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Phone size={24} style={{ color: '#41FFFF' }} />
            <div style={title}>REALTIME VOICE CHAT</div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {isConnected && (
              <button onClick={handleClearTranscripts} style={iconBtn} title="Clear transcripts">
                <Trash2 size={20} />
              </button>
            )}
            <button onClick={onClose} style={iconBtn} title="Close">
              ✕
            </button>
          </div>
        </div>

        {/* Status Badge */}
        <div style={statusContainer}>
          <div style={statusBadge(isConnected)}>
            <div style={statusDot(isConnected)} />
            {isConnected ? 'Connected' : 'Disconnected'}
          </div>
          {isConnected && (
            <div style={statusBadge(isRecording)}>
              <Mic size={14} />
              {isRecording ? 'Recording' : 'Muted'}
            </div>
          )}
        </div>

        {/* Error Message */}
        {error && (
          <div style={errorBox}>
            <strong>Error:</strong> {error}
          </div>
        )}

        {/* Controls */}
        <div style={controls}>
          {!isConnected ? (
            <button
              onClick={handleConnect}
              disabled={isConnecting}
              style={connectBtn(isConnecting)}
            >
              <Phone size={20} />
              {isConnecting ? 'Connecting...' : 'Start Voice Chat'}
            </button>
          ) : (
            <>
              <button
                onClick={toggleRecording}
                style={recordBtn(isRecording)}
                title={isRecording ? 'Mute microphone' : 'Unmute microphone'}
              >
                {isRecording ? <Mic size={20} /> : <MicOff size={20} />}
                {isRecording ? 'Mute' : 'Unmute'}
              </button>
              <button onClick={handleDisconnect} style={disconnectBtn}>
                <PhoneOff size={20} />
                End Call
              </button>
            </>
          )}
        </div>

        {/* Transcripts */}
        {isConnected && (
          <div style={transcriptsContainer}>
            {/* User Transcript */}
            <div style={transcriptSection}>
              <div style={transcriptHeader}>
                <Mic size={16} style={{ color: '#41FFFF' }} />
                <div style={transcriptLabel}>YOU</div>
              </div>
              <div style={transcriptBox}>
                {userTranscript || 'Start speaking...'}
              </div>
            </div>

            {/* Agent Transcript */}
            <div style={transcriptSection}>
              <div style={transcriptHeader}>
                <Phone size={16} style={{ color: '#00D9FF' }} />
                <div style={transcriptLabel}>ASSISTANT</div>
              </div>
              <div style={transcriptBox}>
                {agentTranscript || 'Listening...'}
              </div>
            </div>
          </div>
        )}

        {/* Usage Instructions */}
        {!isConnected && !error && (
          <div style={instructionsBox}>
            <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 8, color: '#41FFFF' }}>
              How to use:
            </div>
            <ul style={{ margin: 0, paddingLeft: 20, lineHeight: 1.8 }}>
              <li>Click "Start Voice Chat" to begin</li>
              <li>Allow microphone access when prompted</li>
              <li>Speak naturally - the AI will respond in real-time</li>
              <li>Low latency for natural conversation</li>
            </ul>
          </div>
        )}
      </div>
    </div>
  );
};

// Styles
const overlay = {
  position: 'fixed',
  inset: 0,
  background: 'rgba(0,0,0,0.9)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 2000,
  backdropFilter: 'blur(10px)',
  padding: 20,
};

const card = {
  background: 'linear-gradient(135deg, #0A0D10 0%, #0E1116 100%)',
  border: '2px solid #41FFFF',
  borderRadius: 16,
  padding: 24,
  width: '100%',
  maxWidth: 800,
  boxShadow: '0 0 60px rgba(65,255,255,0.3)',
  maxHeight: '90vh',
  overflowY: 'auto',
};

const header = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  marginBottom: 16,
};

const title = {
  color: '#F0F3F8',
  fontWeight: 800,
  letterSpacing: '.12em',
  fontSize: 18,
};

const iconBtn = {
  background: 'transparent',
  border: 'none',
  color: '#F0F3F8',
  cursor: 'pointer',
  padding: 8,
  borderRadius: 6,
  transition: 'background 0.2s',
  ':hover': {
    background: 'rgba(65, 255, 255, 0.1)',
  },
};

const statusContainer = {
  display: 'flex',
  gap: 12,
  marginBottom: 16,
  flexWrap: 'wrap',
};

const statusBadge = (active) => ({
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  padding: '6px 12px',
  background: active ? 'rgba(65, 255, 255, 0.1)' : 'rgba(255, 255, 255, 0.05)',
  border: `1px solid ${active ? '#41FFFF' : '#555'}`,
  borderRadius: 20,
  fontSize: 12,
  fontWeight: 600,
  color: active ? '#41FFFF' : '#999',
  letterSpacing: '.05em',
});

const statusDot = (active) => ({
  width: 8,
  height: 8,
  borderRadius: '50%',
  background: active ? '#41FFFF' : '#666',
  boxShadow: active ? '0 0 8px #41FFFF' : 'none',
});

const errorBox = {
  background: 'rgba(255, 50, 50, 0.1)',
  border: '1px solid rgba(255, 50, 50, 0.5)',
  borderRadius: 8,
  padding: 12,
  marginBottom: 16,
  color: '#FF6B6B',
  fontSize: 13,
};

const controls = {
  display: 'flex',
  gap: 12,
  marginBottom: 20,
};

const connectBtn = (disabled) => ({
  flex: 1,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: 10,
  padding: '14px 24px',
  background: disabled ? 'rgba(65, 255, 255, 0.3)' : '#41FFFF',
  color: disabled ? '#666' : '#0A0D10',
  border: 'none',
  borderRadius: 8,
  fontSize: 14,
  fontWeight: 700,
  cursor: disabled ? 'not-allowed' : 'pointer',
  transition: 'all 0.2s',
  opacity: disabled ? 0.6 : 1,
});

const recordBtn = (active) => ({
  flex: 1,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: 10,
  padding: '14px 24px',
  background: active ? '#41FFFF' : 'rgba(65, 255, 255, 0.2)',
  color: active ? '#0A0D10' : '#41FFFF',
  border: `1px solid #41FFFF`,
  borderRadius: 8,
  fontSize: 14,
  fontWeight: 700,
  cursor: 'pointer',
  transition: 'all 0.2s',
});

const disconnectBtn = {
  flex: 1,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: 10,
  padding: '14px 24px',
  background: 'rgba(255, 50, 50, 0.2)',
  color: '#FF6B6B',
  border: '1px solid #FF6B6B',
  borderRadius: 8,
  fontSize: 14,
  fontWeight: 700,
  cursor: 'pointer',
  transition: 'all 0.2s',
};

const transcriptsContainer = {
  display: 'grid',
  gap: 16,
  gridTemplateColumns: '1fr 1fr',
};

const transcriptSection = {
  display: 'flex',
  flexDirection: 'column',
  gap: 8,
};

const transcriptHeader = {
  display: 'flex',
  gap: 8,
  alignItems: 'center',
};

const transcriptLabel = {
  color: '#F0F3F8',
  fontSize: 11,
  letterSpacing: '.12em',
  fontWeight: 800,
};

const transcriptBox = {
  minHeight: 200,
  maxHeight: 300,
  background: 'rgba(14, 17, 22, 0.6)',
  border: '1px solid rgba(65, 255, 255, 0.25)',
  borderRadius: 8,
  padding: 12,
  color: '#E6EDF6',
  fontSize: 13,
  lineHeight: 1.6,
  whiteSpace: 'pre-wrap',
  overflowY: 'auto',
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
};

const instructionsBox = {
  background: 'rgba(65, 255, 255, 0.05)',
  border: '1px solid rgba(65, 255, 255, 0.2)',
  borderRadius: 8,
  padding: 16,
  color: '#A2A7AF',
  fontSize: 13,
  lineHeight: 1.6,
};

export default RealtimeVoiceChat;
