// frontend/src/hooks/useWebRTC.js
/**
 * useWebRTC Hook for OpenAI Realtime Voice API with WebRTC
 *
 * This hook establishes a direct, low-latency WebRTC connection to OpenAI's
 * Realtime API for voice interaction with minimal latency.
 *
 * Key Features:
 * - Direct browser-to-OpenAI WebRTC connection
 * - Real-time audio streaming with echo cancellation
 * - Progressive transcript rendering with delta updates
 * - Low-latency speech-to-speech communication
 */

import { useState, useRef, useEffect, useCallback } from 'react';

/**
 * useWebRTC Hook
 *
 * @param {Object} config - Configuration options
 * @param {string} config.model - OpenAI model to use (default: "gpt-4o-realtime-preview-2024-12-17")
 * @param {string} config.transcriptionModel - Transcription model (default: "whisper-1")
 * @param {string} config.voice - Voice to use for TTS (default: "alloy")
 * @param {Function} config.onTranscriptDelta - Callback for transcript delta updates
 * @param {Function} config.onTranscriptDone - Callback for completed transcript
 * @param {Function} config.onAgentResponse - Callback for agent audio response
 * @param {Function} config.onError - Callback for errors
 * @returns {Object} WebRTC session controls
 */
export const useWebRTC = ({
  model = "gpt-4o-realtime-preview-2024-12-17",
  transcriptionModel = "whisper-1",
  voice = "alloy",
  onTranscriptDelta = () => {},
  onTranscriptDone = () => {},
  onAgentResponse = () => {},
  onError = () => {},
} = {}) => {
  const [isConnected, setIsConnected] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [userTranscript, setUserTranscript] = useState("");
  const [agentTranscript, setAgentTranscript] = useState("");

  const peerConnectionRef = useRef(null);
  const dataChannelRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const audioElementRef = useRef(null);
  const ephemeralKeyRef = useRef(null);

  /**
   * Initialize audio element for playback
   */
  useEffect(() => {
    if (!audioElementRef.current) {
      audioElementRef.current = new Audio();
      audioElementRef.current.autoplay = true;
    }

    return () => {
      if (audioElementRef.current) {
        audioElementRef.current.pause();
        audioElementRef.current.src = '';
      }
    };
  }, []);

  /**
   * Get ephemeral key from backend
   */
  const getEphemeralKey = async () => {
    try {
      const response = await fetch('/api/realtime/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      if (!response.ok) {
        throw new Error('Failed to get ephemeral key');
      }

      const data = await response.json();
      return data.ephemeral_key;
    } catch (error) {
      console.error('Error getting ephemeral key:', error);
      onError(error);
      throw error;
    }
  };

  /**
   * Handle incoming data channel messages
   */
  const handleDataChannelMessage = useCallback((event) => {
    try {
      const message = JSON.parse(event.data);
      const { type, transcript, delta, audio } = message;

      // Handle user transcript delta
      if (type === "input_audio_transcription.delta") {
        const text = delta || transcript?.text || "";
        if (text) {
          setUserTranscript(prev => prev + text);
          onTranscriptDelta({ type: "user", text });
        }
      }

      // Handle user transcript completion
      if (type === "input_audio_transcription.completed") {
        const fullText = transcript?.text || "";
        if (fullText) {
          setUserTranscript(fullText);
          onTranscriptDone({ type: "user", text: fullText });
        }
      }

      // Handle agent response delta
      if (type === "response.audio_transcript.delta") {
        const text = delta || transcript?.text || "";
        if (text) {
          setAgentTranscript(prev => prev + text);
          onTranscriptDelta({ type: "agent", text });
        }
      }

      // Handle agent response completion
      if (type === "response.audio_transcript.done") {
        const fullText = transcript?.text || "";
        if (fullText) {
          setAgentTranscript(fullText);
          onTranscriptDone({ type: "agent", text: fullText });
        }
      }

      // Handle agent audio response
      if (type === "response.audio.delta" && audio) {
        onAgentResponse(audio);
      }

      // Handle errors
      if (type === "error") {
        console.error('Realtime API error:', message);
        onError(new Error(message.error?.message || 'Unknown error'));
      }
    } catch (error) {
      console.error('Error handling data channel message:', error);
      onError(error);
    }
  }, [onTranscriptDelta, onTranscriptDone, onAgentResponse, onError]);

  /**
   * Setup data channel event handlers
   */
  const setupDataChannel = useCallback((channel) => {
    channel.addEventListener('open', () => {
      console.log('Data channel opened');

      // Send session configuration
      channel.send(JSON.stringify({
        type: 'session.update',
        session: {
          modalities: ['text', 'audio'],
          instructions: 'You are a helpful AI assistant. Respond naturally and conversationally.',
          voice: voice,
          input_audio_format: 'pcm16',
          output_audio_format: 'pcm16',
          input_audio_transcription: {
            model: transcriptionModel
          },
          turn_detection: {
            type: 'server_vad',
            threshold: 0.5,
            prefix_padding_ms: 300,
            silence_duration_ms: 500
          }
        }
      }));
    });

    channel.addEventListener('message', handleDataChannelMessage);

    channel.addEventListener('close', () => {
      console.log('Data channel closed');
      setIsConnected(false);
    });

    channel.addEventListener('error', (error) => {
      console.error('Data channel error:', error);
      onError(error);
    });

    dataChannelRef.current = channel;
  }, [voice, transcriptionModel, handleDataChannelMessage, onError]);

  /**
   * Connect to OpenAI Realtime API via WebRTC
   */
  const connect = async () => {
    try {
      // Get ephemeral key from backend
      const ephemeralKey = await getEphemeralKey();
      ephemeralKeyRef.current = ephemeralKey;

      // Create peer connection
      const peerConnection = new RTCPeerConnection();
      peerConnectionRef.current = peerConnection;

      // Setup audio element for remote stream
      peerConnection.ontrack = (event) => {
        if (audioElementRef.current) {
          audioElementRef.current.srcObject = event.streams[0];
        }
      };

      // Setup data channel
      const dataChannel = peerConnection.createDataChannel('oai-events');
      setupDataChannel(dataChannel);

      // Get user media with optimized settings for low latency
      const mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          sampleRate: 24000,
          channelCount: 1
        }
      });
      mediaStreamRef.current = mediaStream;

      // Add audio track to peer connection
      mediaStream.getTracks().forEach(track => {
        peerConnection.addTrack(track, mediaStream);
      });

      // Create and set local offer
      const offer = await peerConnection.createOffer();
      await peerConnection.setLocalDescription(offer);

      // Send offer to OpenAI Realtime API
      const sdpResponse = await fetch(
        `https://api.openai.com/v1/realtime?model=${model}`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${ephemeralKey}`,
            'Content-Type': 'application/sdp'
          },
          body: offer.sdp
        }
      );

      if (!sdpResponse.ok) {
        throw new Error('Failed to connect to OpenAI Realtime API');
      }

      const answerSdp = await sdpResponse.text();
      await peerConnection.setRemoteDescription({
        type: 'answer',
        sdp: answerSdp
      });

      setIsConnected(true);
      setIsRecording(true);

      console.log('Successfully connected to OpenAI Realtime API');
    } catch (error) {
      console.error('Error connecting to OpenAI Realtime API:', error);
      onError(error);
      disconnect();
      throw error;
    }
  };

  /**
   * Disconnect from OpenAI Realtime API
   */
  const disconnect = useCallback(() => {
    // Stop media stream
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(track => track.stop());
      mediaStreamRef.current = null;
    }

    // Close data channel
    if (dataChannelRef.current) {
      dataChannelRef.current.close();
      dataChannelRef.current = null;
    }

    // Close peer connection
    if (peerConnectionRef.current) {
      peerConnectionRef.current.close();
      peerConnectionRef.current = null;
    }

    // Stop audio playback
    if (audioElementRef.current) {
      audioElementRef.current.pause();
      audioElementRef.current.srcObject = null;
    }

    setIsConnected(false);
    setIsRecording(false);
    setUserTranscript("");
    setAgentTranscript("");

    console.log('Disconnected from OpenAI Realtime API');
  }, []);

  /**
   * Send a text message to the agent
   */
  const sendMessage = useCallback((text) => {
    if (!dataChannelRef.current || dataChannelRef.current.readyState !== 'open') {
      console.error('Data channel is not open');
      return;
    }

    try {
      dataChannelRef.current.send(JSON.stringify({
        type: 'conversation.item.create',
        item: {
          type: 'message',
          role: 'user',
          content: [{
            type: 'input_text',
            text: text
          }]
        }
      }));

      // Trigger response
      dataChannelRef.current.send(JSON.stringify({
        type: 'response.create'
      }));
    } catch (error) {
      console.error('Error sending message:', error);
      onError(error);
    }
  }, [onError]);

  /**
   * Toggle audio recording
   */
  const toggleRecording = useCallback(() => {
    if (!mediaStreamRef.current) return;

    const audioTrack = mediaStreamRef.current.getAudioTracks()[0];
    if (audioTrack) {
      audioTrack.enabled = !audioTrack.enabled;
      setIsRecording(audioTrack.enabled);
    }
  }, []);

  /**
   * Clear transcripts
   */
  const clearTranscripts = useCallback(() => {
    setUserTranscript("");
    setAgentTranscript("");
  }, []);

  /**
   * Cleanup on unmount
   */
  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return {
    isConnected,
    isRecording,
    userTranscript,
    agentTranscript,
    connect,
    disconnect,
    sendMessage,
    toggleRecording,
    clearTranscripts
  };
};

export default useWebRTC;
