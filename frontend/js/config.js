/**
 * config.js — Application Configuration
 * ======================================
 * Centralised constants and backend URL configuration.
 */

const CONFIG = Object.freeze({
  // Backend base URL (FastAPI server)
  API_BASE: 'http://localhost:8000',

  // Endpoints
  ENDPOINTS: {
    HEALTH:   '/health',
    CHAT:     '/chat',
    STT:      '/stt',
    TTS:      '/tts',
    VIDEO:    '/video',
    SNAPSHOT: '/snapshot',
    VISION:   '/vision',
  },

  // Health-check polling interval (ms)
  HEALTH_POLL_INTERVAL: 10000,

  // Default chat settings
  DEFAULT_TEMPERATURE: 0.7,
  MAX_MESSAGE_LENGTH:  8000,

  // Voice settings
  AUDIO_MIME_TYPE: 'audio/webm',
  MAX_RECORDING_MS: 120000,  // 2 minutes

  // Session
  SESSION_STORAGE_KEY: 'ai_assistant_sessions',
  ACTIVE_SESSION_KEY:  'ai_assistant_active_session',
});
