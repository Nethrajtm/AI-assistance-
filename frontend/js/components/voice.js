/**
 * voice.js — Voice I/O Component
 * ================================
 * Microphone recording via MediaRecorder → STT,
 * TTS playback, audio waveform visualisation.
 */

const VoiceComponent = {
    _els: {},
    _mediaRecorder: null,
    _audioChunks: [],
    _audioContext: null,
    _analyser: null,
    _animFrameId: null,
    _currentAudio: null,

    // ----------------------------------------------------------------
    //  Init
    // ----------------------------------------------------------------

    init() {
        this._els = {
            visualizer: document.getElementById('voice-visualizer'),
            voiceIcon: document.getElementById('voice-icon'),
            recordBtn: document.getElementById('btn-record'),
            playBtn: document.getElementById('btn-play-recording'),
            status: document.getElementById('voice-status'),
            transcript: document.getElementById('voice-transcript'),
            transcriptTx: document.getElementById('transcript-text'),
            ttsInput: document.getElementById('tts-input'),
            ttsBtn: document.getElementById('btn-tts'),
            barsContainer: document.getElementById('voice-bars'),
        };

        // Create visualisation bars
        for (let i = 0; i < 24; i++) {
            const bar = document.createElement('div');
            bar.className = 'voice-bar';
            bar.style.height = '4px';
            this._els.barsContainer.appendChild(bar);
        }

        this._bindEvents();
    },

    // ----------------------------------------------------------------
    //  Event Bindings
    // ----------------------------------------------------------------

    _bindEvents() {
        // Record toggle
        this._els.recordBtn.addEventListener('click', () => {
            if (AppState.isRecording) {
                this._stopRecording();
            } else {
                this._startRecording();
            }
        });

        // Play recording
        this._els.playBtn.addEventListener('click', () => {
            this._playRecording();
        });

        // TTS
        this._els.ttsBtn.addEventListener('click', () => {
            this._textToSpeech();
        });

        // TTS on Enter key
        this._els.ttsInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                this._textToSpeech();
            }
        });
    },

    // ----------------------------------------------------------------
    //  Recording
    // ----------------------------------------------------------------

    async _startRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

            this._audioChunks = [];
            this._mediaRecorder = new MediaRecorder(stream, {
                mimeType: MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/mp4',
            });

            this._mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) this._audioChunks.push(e.data);
            };

            this._mediaRecorder.onstop = () => {
                const blob = new Blob(this._audioChunks, { type: this._mediaRecorder.mimeType });
                AppState.audioBlob = blob;
                this._els.playBtn.disabled = false;

                // Stop stream tracks
                stream.getTracks().forEach(t => t.stop());

                // Auto-transcribe
                this._transcribe(blob);
            };

            this._mediaRecorder.start(250); // collect data every 250ms

            AppState.isRecording = true;
            this._els.visualizer.classList.add('recording');
            this._els.recordBtn.classList.add('active');
            this._setStatus('Recording…', 'Speak clearly into your microphone');

            // Start visualisation
            this._startVisualization(stream);

        } catch (err) {
            Toast.error('Microphone access denied or unavailable');
            console.error('Recording error:', err);
        }
    },

    _stopRecording() {
        if (this._mediaRecorder && this._mediaRecorder.state !== 'inactive') {
            this._mediaRecorder.stop();
        }
        AppState.isRecording = false;
        this._els.visualizer.classList.remove('recording');
        this._els.recordBtn.classList.remove('active');
        this._stopVisualization();
        this._setStatus('Processing…', 'Transcribing your audio…');
    },

    // ----------------------------------------------------------------
    //  Transcription (STT)
    // ----------------------------------------------------------------

    async _transcribe(blob) {
        try {
            const result = await API.stt(blob);
            AppState.lastTranscript = result.text;
            this._els.transcript.style.display = 'block';
            this._els.transcriptTx.textContent = result.text;
            this._setStatus('Done', `Transcribed ${result.duration_seconds ? result.duration_seconds.toFixed(1) + 's' : ''} of audio`);
            Toast.success('Audio transcribed successfully');
        } catch (err) {
            this._setStatus('Error', err.message);
            Toast.error(`STT failed: ${err.message}`);
        }
    },

    // ----------------------------------------------------------------
    //  Play Recording
    // ----------------------------------------------------------------

    _playRecording() {
        if (!AppState.audioBlob) return;

        if (this._currentAudio) {
            this._currentAudio.pause();
            this._currentAudio = null;
            this._els.visualizer.classList.remove('playing');
            return;
        }

        const url = URL.createObjectURL(AppState.audioBlob);
        this._currentAudio = new Audio(url);
        this._els.visualizer.classList.add('playing');

        this._currentAudio.onended = () => {
            this._els.visualizer.classList.remove('playing');
            this._currentAudio = null;
            URL.revokeObjectURL(url);
        };

        this._currentAudio.play();
    },

    // ----------------------------------------------------------------
    //  Text-to-Speech
    // ----------------------------------------------------------------

    async _textToSpeech() {
        const text = this._els.ttsInput.value.trim();
        if (!text) return;

        this._els.ttsBtn.disabled = true;
        this._els.ttsBtn.textContent = '⏳ Generating…';

        try {
            const audioBlob = await API.tts(text);
            const url = URL.createObjectURL(audioBlob);
            const audio = new Audio(url);

            this._els.visualizer.classList.add('playing');
            audio.onended = () => {
                this._els.visualizer.classList.remove('playing');
                URL.revokeObjectURL(url);
            };

            await audio.play();
            Toast.success('Playing speech');
        } catch (err) {
            Toast.error(`TTS failed: ${err.message}`);
        } finally {
            this._els.ttsBtn.disabled = false;
            this._els.ttsBtn.textContent = '🔊 Speak';
        }
    },

    // ----------------------------------------------------------------
    //  Audio Visualisation
    // ----------------------------------------------------------------

    _startVisualization(stream) {
        this._audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const source = this._audioContext.createMediaStreamSource(stream);
        this._analyser = this._audioContext.createAnalyser();
        this._analyser.fftSize = 64;
        source.connect(this._analyser);

        const bars = this._els.barsContainer.children;
        const dataArray = new Uint8Array(this._analyser.frequencyBinCount);

        const draw = () => {
            this._animFrameId = requestAnimationFrame(draw);
            this._analyser.getByteFrequencyData(dataArray);

            for (let i = 0; i < bars.length; i++) {
                const val = dataArray[i] || 0;
                const h = Math.max(4, (val / 255) * 60);
                bars[i].style.height = h + 'px';
                bars[i].style.opacity = 0.4 + (val / 255) * 0.6;
            }
        };
        draw();
    },

    _stopVisualization() {
        if (this._animFrameId) cancelAnimationFrame(this._animFrameId);
        if (this._audioContext) this._audioContext.close().catch(() => { });

        const bars = this._els.barsContainer.children;
        for (let i = 0; i < bars.length; i++) {
            bars[i].style.height = '4px';
            bars[i].style.opacity = '1';
        }
    },

    // ----------------------------------------------------------------
    //  Helpers
    // ----------------------------------------------------------------

    _setStatus(label, detail) {
        this._els.status.innerHTML = `
      <div class="label">${label}</div>
      <div>${detail || ''}</div>
    `;
    },
};
