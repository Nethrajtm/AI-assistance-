/**
 * api.js — Backend API Client
 * ============================
 * Centralised HTTP layer that talks to the FastAPI backend.
 * Every public function returns a Promise.
 */

const API = {
    /**
     * Build the full URL for an endpoint.
     * @param {string} path
     * @returns {string}
     */
    _url(path) {
        return CONFIG.API_BASE + path;
    },

    // ==============================================================
    //  Health
    // ==============================================================

    /**
     * Check backend health.
     * @returns {Promise<object>}
     */
    async health() {
        const res = await fetch(this._url(CONFIG.ENDPOINTS.HEALTH));
        if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
        return res.json();
    },

    // ==============================================================
    //  Chat (non-streaming)
    // ==============================================================

    /**
     * Send a chat message (non-streaming mode).
     * @param {object} payload - { session_id, messages, stream:false, ... }
     * @returns {Promise<object>}
     */
    async chat(payload) {
        const res = await fetch(this._url(CONFIG.ENDPOINTS.CHAT), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...payload, stream: false }),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.error || `Chat failed: ${res.status}`);
        }
        return res.json();
    },

    // ==============================================================
    //  Chat (SSE streaming)
    // ==============================================================

    /**
     * Open an SSE stream for chat.  Calls `onToken` for each token,
     * `onToolCall` for tool invocations, `onDone` on completion,
     * and `onError` on failure.
     *
     * @param {object} payload  - ChatRequest body with stream:true
     * @param {object} callbacks
     * @param {Function} callbacks.onToken    - (tokenStr) =>
     * @param {Function} callbacks.onToolCall - (toolCallObj) =>
     * @param {Function} callbacks.onDone     - (fullText) =>
     * @param {Function} callbacks.onError    - (errorStr) =>
     * @returns {AbortController}  Call .abort() to cancel the stream.
     */
    chatStream(payload, { onToken, onToolCall, onDone, onError }) {
        const controller = new AbortController();

        fetch(this._url(CONFIG.ENDPOINTS.CHAT), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...payload, stream: true }),
            signal: controller.signal,
        })
            .then(async (res) => {
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.error || `Stream failed: ${res.status}`);
                }

                const reader = res.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                let fullText = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });

                    // Parse SSE lines
                    const lines = buffer.split('\n');
                    buffer = lines.pop(); // keep incomplete line in buffer

                    for (const line of lines) {
                        const trimmed = line.trim();
                        if (!trimmed || trimmed.startsWith(':')) continue; // skip empty or comments

                        if (trimmed.startsWith('data: ')) {
                            const data = trimmed.slice(6);

                            if (data === '[DONE]') {
                                if (onDone) onDone(fullText);
                                return;
                            }

                            try {
                                const parsed = JSON.parse(data);

                                if (parsed.error) {
                                    if (onError) onError(parsed.error);
                                    return;
                                }

                                if (parsed.tool_call && onToolCall) {
                                    onToolCall(parsed.tool_call);
                                } else if (parsed.token !== undefined) {
                                    fullText += parsed.token;
                                    if (onToken) onToken(parsed.token);
                                } else if (parsed.content !== undefined) {
                                    fullText += parsed.content;
                                    if (onToken) onToken(parsed.content);
                                } else if (typeof parsed === 'string') {
                                    fullText += parsed;
                                    if (onToken) onToken(parsed);
                                }
                            } catch {
                                // Treat unparseable data as raw token text
                                fullText += data;
                                if (onToken) onToken(data);
                            }
                        }
                    }
                }

                // Stream ended without [DONE]
                if (onDone) onDone(fullText);
            })
            .catch((err) => {
                if (err.name !== 'AbortError') {
                    if (onError) onError(err.message);
                }
            });

        return controller;
    },

    // ==============================================================
    //  Speech-to-Text
    // ==============================================================

    /**
     * Transcribe an audio blob.
     * @param {Blob} audioBlob
     * @param {string} [language]
     * @returns {Promise<object>}
     */
    async stt(audioBlob, language) {
        const form = new FormData();
        form.append('file', audioBlob, 'recording.webm');
        if (language) form.append('language', language);

        const res = await fetch(this._url(CONFIG.ENDPOINTS.STT), {
            method: 'POST',
            body: form,
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.error || `STT failed: ${res.status}`);
        }
        return res.json();
    },

    // ==============================================================
    //  Text-to-Speech
    // ==============================================================

    /**
     * Convert text to speech audio.
     * @param {string} text
     * @param {string} [voice]
     * @returns {Promise<Blob>}
     */
    async tts(text, voice) {
        const res = await fetch(this._url(CONFIG.ENDPOINTS.TTS), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, voice }),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.error || `TTS failed: ${res.status}`);
        }
        return res.blob();
    },

    // ==============================================================
    //  Vision
    // ==============================================================

    /**
     * Analyse an image with a text prompt.
     * @param {object} opts
     * @param {string} opts.prompt
     * @param {File|Blob} [opts.image]
     * @param {string} [opts.imageUrl]
     * @param {string} [opts.sessionId]
     * @returns {Promise<object>}
     */
    async vision({ prompt, image, imageUrl, sessionId }) {
        const form = new FormData();
        form.append('prompt', prompt);
        if (image) form.append('image', image);
        if (imageUrl) form.append('image_url', imageUrl);
        if (sessionId) form.append('session_id', sessionId);

        const res = await fetch(this._url(CONFIG.ENDPOINTS.VISION), {
            method: 'POST',
            body: form,
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.error || `Vision failed: ${res.status}`);
        }
        return res.json();
    },

    // ==============================================================
    //  Camera
    // ==============================================================

    /**
     * Get the MJPEG stream URL (used as img src).
     * @returns {string}
     */
    videoStreamUrl() {
        return this._url(CONFIG.ENDPOINTS.VIDEO);
    },

    /**
     * Capture a single JPEG snapshot.
     * @returns {Promise<Blob>}
     */
    async snapshot() {
        const res = await fetch(this._url(CONFIG.ENDPOINTS.SNAPSHOT));
        if (!res.ok) throw new Error(`Snapshot failed: ${res.status}`);
        return res.blob();
    },
};
