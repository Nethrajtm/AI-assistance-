# Multimodal AI Assistant — Backend

Enterprise-ready FastAPI backend for a multimodal AI assistant with LLM chat, vision, voice I/O, tools, memory, and safety filtering.

## Quick Start

```bash
# 1. Clone & enter the project
cd AI

# 2. Create a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux / macOS

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
copy .env.example .env
# Edit .env and add your API keys

# 5. Run the server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The API docs are available at **http://localhost:8000/docs** (Swagger UI).

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `openai` | `openai` / `anthropic` / `ollama` |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o` | Model name |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Local Ollama URL |
| `VISION_PROVIDER` | `openai` | Vision LLM provider |
| `TTS_PROVIDER` | `openai` | `openai` / `elevenlabs` |
| `STT_PROVIDER` | `openai` | Speech-to-text provider |
| `SHORT_TERM_MEMORY_LIMIT` | `50` | Messages kept per session |
| `RATE_LIMIT_MAX_REQUESTS` | `30` | Max requests per window |
| `TOOL_WORKSPACE_DIR` | `./workspace` | Sandboxed file I/O path |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed origins (JSON) |

See `.env.example` for the full list.

---

## Endpoints

### `GET /health`
```bash
curl http://localhost:8000/health
```
```json
{"status": "ok", "timestamp": "...", "version": "1.0.0", "provider": "openai"}
```

### `POST /chat` — Conversational AI
```bash
# Non-streaming
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "user-123",
    "messages": [{"role": "user", "content": "What is 42 * 17?"}],
    "stream": false
  }'

# Streaming (SSE)
curl -N -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "user-123",
    "messages": [{"role": "user", "content": "Tell me a story"}],
    "stream": true
  }'
```

### `POST /stt` — Speech-to-Text
```bash
curl -X POST http://localhost:8000/stt \
  -F "file=@recording.wav"
```

### `POST /tts` — Text-to-Speech
```bash
curl -X POST http://localhost:8000/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello, how can I help you?"}' \
  --output speech.mp3
```

### `GET /video` — MJPEG Camera Stream
```bash
# Open in browser or use:
curl http://localhost:8000/video --output stream.mjpeg
```

### `GET /snapshot` — Single Camera Frame
```bash
curl http://localhost:8000/snapshot --output frame.jpg
```

### `POST /vision` — Image Analysis
```bash
# With file upload
curl -X POST http://localhost:8000/vision \
  -F "prompt=Describe this image" \
  -F "image=@photo.jpg"

# With image URL
curl -X POST http://localhost:8000/vision \
  -F "prompt=What's in this picture?" \
  -F "image_url=https://example.com/photo.jpg"
```

---

## Architecture

```
main.py          → FastAPI app, routes, middleware
├── llm.py       → LLM provider abstraction (OpenAI, Anthropic, Ollama)
├── memory.py    → Short-term + ChromaDB RAG memory
├── tools.py     → Tool registry + calculator, search, file I/O
├── safety.py    → Jailbreak detection, output filtering, rate limiting
├── stt.py       → Speech-to-text (Whisper)
├── tts.py       → Text-to-speech (OpenAI / ElevenLabs)
├── camera.py    → OpenCV MJPEG streaming & snapshots
├── vision.py    → Multimodal image analysis
├── schemas.py   → Pydantic request/response models
└── config.py    → Environment variable management
```

## Built-in Tools

| Tool | Description |
|---|---|
| `calculator` | Safe math expression evaluation (no `eval()`) |
| `web_search` | DuckDuckGo instant answers |
| `file_read` | Read files from sandboxed workspace |
| `file_write` | Write files to sandboxed workspace |

## Safety Features

- **Jailbreak detection**: 8 regex-based patterns (DAN, prompt injection, token smuggling, etc.)
- **Output filtering**: blocks harmful content (violence, self-harm, hate speech, doxxing)
- **Rate limiting**: per-session sliding window (configurable)
- **Prompt sanitisation**: strips chat-template injection tokens
- **All events logged** at WARNING level for monitoring

---

## License

MIT
