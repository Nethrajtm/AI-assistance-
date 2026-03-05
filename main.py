"""
main.py — FastAPI Application Entry Point
===========================================
Wires together all modules into a production-ready web server:
  - Lifecycle events (startup / shutdown)
  - CORS middleware
  - Request logging middleware
  - Global exception handler
  - Seven HTTP endpoints: /health, /chat, /stt, /tts, /video, /snapshot, /vision

Run with:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sse_starlette.sse import EventSourceResponse

from config import configure_logging, settings
from schemas import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    HealthResponse,
    Message,
    STTResponse,
    TTSRequest,
    ToolCall,
    ToolResult,
    VisionRequest,
    VisionResponse,
)

# Import application modules
from llm import LLMClient
from memory import MemoryManager
from tools import create_default_registry
from safety import check_prompt_safety, check_output_safety, check_rate_limit, sanitise_prompt
from stt import transcribe_audio
from tts import synthesise_speech, stream_speech
from camera import camera_manager, mjpeg_stream, capture_snapshot
from vision import analyse_image

logger = logging.getLogger(__name__)

# ============================================================
# Application State (initialised in lifespan)
# ============================================================

llm_client: LLMClient
memory_mgr: MemoryManager
tool_registry = create_default_registry()


# ============================================================
# Lifespan (startup & shutdown hooks)
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage resources that live for the entire server process."""
    global llm_client, memory_mgr

    configure_logging()
    logger.info("Starting Multimodal AI Assistant backend …")

    # Initialise core services
    llm_client = LLMClient()
    memory_mgr = MemoryManager()

    logger.info("All services initialised. Server ready.")
    yield  # ---- application runs here ----

    # Shutdown
    logger.info("Shutting down …")
    await llm_client.close()
    camera_manager.stop()
    logger.info("Shutdown complete.")


# ============================================================
# FastAPI App
# ============================================================

app = FastAPI(
    title="Multimodal AI Assistant",
    description="Enterprise-ready backend for LLM chat, vision, voice, tools, and safety.",
    version="1.0.0",
    lifespan=lifespan,
)

# ---- CORS ----
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Request Logging Middleware ----

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every inbound request with timing."""
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    logger.info(
        "%s %s → %d (%.3fs)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed,
    )
    return response


# ---- Global Exception Handler ----

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler so unhandled errors return structured JSON."""
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal server error",
            detail=str(exc),
            status_code=500,
        ).model_dump(),
    )


# ============================================================
# 1. GET /health
# ============================================================

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check() -> HealthResponse:
    """Return server health status."""
    return HealthResponse(
        status="ok",
        timestamp=datetime.utcnow(),
        version="1.0.0",
        provider=settings.llm_provider,
    )


# ============================================================
# 2. POST /chat
# ============================================================

@app.post("/chat", tags=["Chat"])
async def chat_endpoint(request: ChatRequest):
    """
    Main conversational endpoint.

    - Accepts ``session_id``, ``messages``, optional ``tools``, and ``stream`` flag.
    - Runs safety pre-checks (rate limit, jailbreak detection).
    - Builds context from memory (short-term + RAG).
    - Calls the LLM (streaming or non-streaming).
    - Runs safety post-checks on the response.
    - Stores messages in memory.
    """
    session_id = request.session_id

    # ---- Rate Limiting ----
    rate_ok, rate_reason = check_rate_limit(session_id)
    if not rate_ok:
        raise HTTPException(status_code=429, detail=rate_reason)

    # ---- Jailbreak Detection (on latest user message) ----
    latest_user_msg = next(
        (m for m in reversed(request.messages) if m.role == "user"), None
    )
    if latest_user_msg:
        safe, reason = check_prompt_safety(latest_user_msg.content, session_id)
        if not safe:
            raise HTTPException(status_code=400, detail=reason)
        # Sanitise
        latest_user_msg.content = sanitise_prompt(latest_user_msg.content)

    # ---- Build context from memory ----
    rag_query = latest_user_msg.content if latest_user_msg else None
    context = memory_mgr.build_context(session_id, request.messages, rag_query=rag_query)
    context_messages = [Message(role=m["role"], content=m["content"]) for m in context]

    # ---- Resolve tool definitions ----
    tool_defs = request.tools or tool_registry.get_definitions()

    # ---- Streaming response ----
    if request.stream:
        async def event_generator():
            full_response = ""
            try:
                async for token in llm_client.stream_chat(
                    context_messages,
                    model=request.model,
                    temperature=request.temperature,
                ):
                    full_response += token
                    yield {"event": "token", "data": json.dumps({"token": token})}
                # Post-process the full response
                out_safe, out_reason = check_output_safety(full_response, session_id)
                if not out_safe:
                    yield {"event": "error", "data": json.dumps({"error": out_reason})}
                else:
                    yield {"event": "done", "data": json.dumps({"content": full_response})}
                # Store in memory
                for msg in request.messages:
                    memory_mgr.add_message(session_id, msg)
                memory_mgr.add_message(
                    session_id,
                    Message(role="assistant", content=full_response),
                )
            except Exception as exc:
                logger.error("Streaming error: %s", exc)
                yield {"event": "error", "data": json.dumps({"error": str(exc)})}

        return EventSourceResponse(event_generator())

    # ---- Non-streaming response ----
    try:
        result = await llm_client.chat(
            context_messages,
            model=request.model,
            temperature=request.temperature,
            tools=tool_defs,
        )
    except Exception as exc:
        logger.error("LLM chat error: %s", exc)
        raise HTTPException(status_code=502, detail=f"LLM provider error: {exc}")

    assistant_content = result.get("content", "")

    # ---- Tool execution (if LLM requested tools) ----
    tool_calls_raw = result.get("tool_calls", [])
    tool_calls = []
    tool_results = []

    if tool_calls_raw:
        for tc in tool_calls_raw:
            # Normalise structure across providers
            if isinstance(tc, dict):
                call_id = tc.get("id", "")
                func = tc.get("function", tc)
                name = func.get("name", "")
                args_raw = func.get("arguments", "{}")
                args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
            else:
                continue

            tool_calls.append(ToolCall(id=call_id, name=name, arguments=args))
            tr = await tool_registry.execute(name, args, call_id)
            tool_results.append(tr)

        # If tools were called, send results back to LLM for final answer
        tool_context = list(context_messages)
        tool_context.append(Message(role="assistant", content=assistant_content or ""))
        for tr in tool_results:
            tool_context.append(
                Message(
                    role="tool",
                    content=json.dumps({"name": tr.name, "result": tr.result, "error": tr.error}),
                    tool_call_id=tr.tool_call_id,
                )
            )
        try:
            final = await llm_client.chat(tool_context, model=request.model, temperature=request.temperature)
            assistant_content = final.get("content", assistant_content)
        except Exception as exc:
            logger.warning("Second LLM call after tools failed: %s", exc)

    # ---- Output safety check ----
    out_safe, out_reason = check_output_safety(assistant_content, session_id)
    if not out_safe:
        assistant_content = (
            "I'm sorry, I can't provide that information. "
            "My response was filtered for safety reasons."
        )

    # ---- Store in memory ----
    for msg in request.messages:
        memory_mgr.add_message(session_id, msg)
    assistant_msg = Message(role="assistant", content=assistant_content)
    memory_mgr.add_message(session_id, assistant_msg)

    return ChatResponse(
        session_id=session_id,
        message=assistant_msg,
        tool_calls=tool_calls or None,
        tool_results=tool_results or None,
        usage=result.get("usage"),
    )


# ============================================================
# 3. POST /stt  —  Speech-to-Text
# ============================================================

@app.post("/stt", response_model=STTResponse, tags=["Voice"])
async def stt_endpoint(
    file: UploadFile = File(..., description="Audio file (WAV, MP3, M4A, etc.)"),
    language: str = Form(None, description="Optional ISO-639-1 language hint"),
) -> STTResponse:
    """Transcribe an uploaded audio file to text."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded.")

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        result = await transcribe_audio(audio_bytes, filename=file.filename, language=language)
        return STTResponse(
            text=result["text"],
            language=result.get("language"),
            duration_seconds=result.get("duration_seconds"),
        )
    except Exception as exc:
        logger.error("STT error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Transcription failed: {exc}")


# ============================================================
# 4. POST /tts  —  Text-to-Speech
# ============================================================

@app.post("/tts", tags=["Voice"])
async def tts_endpoint(request: TTSRequest):
    """Convert text to speech audio (MP3)."""
    try:
        audio_bytes = await synthesise_speech(
            text=request.text,
            voice=request.voice,
            model=request.model,
        )
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={"Content-Disposition": "attachment; filename=speech.mp3"},
        )
    except Exception as exc:
        logger.error("TTS error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Speech synthesis failed: {exc}")


# ============================================================
# 5. GET /video  —  MJPEG Camera Stream
# ============================================================

@app.get("/video", tags=["Camera"])
async def video_stream():
    """Stream live camera feed as MJPEG."""
    return StreamingResponse(
        mjpeg_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# ============================================================
# 6. GET /snapshot  —  Single JPEG Frame
# ============================================================

@app.get("/snapshot", tags=["Camera"])
async def snapshot_endpoint():
    """Capture and return a single JPEG frame from the camera."""
    frame = await capture_snapshot()
    if frame is None:
        raise HTTPException(
            status_code=503,
            detail="Camera unavailable — could not capture frame.",
        )
    return Response(content=frame, media_type="image/jpeg")


# ============================================================
# 7. POST /vision  —  Image + Text Analysis
# ============================================================

@app.post("/vision", response_model=VisionResponse, tags=["Vision"])
async def vision_endpoint(
    prompt: str = Form(..., description="Text prompt for the vision model"),
    image: UploadFile = File(None, description="Image file upload"),
    image_url: str = Form(None, description="URL of the image to analyse"),
    session_id: str = Form(None, description="Optional session ID for memory"),
):
    """
    Analyse an image with a text prompt using a vision-capable LLM.
    Either upload a file or provide an image URL.
    """
    image_bytes = None
    mime_type = "image/jpeg"

    if image and image.filename:
        image_bytes = await image.read()
        # Infer MIME type from extension
        ext = image.filename.rsplit(".", 1)[-1].lower() if "." in image.filename else "jpg"
        mime_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp"}
        mime_type = mime_map.get(ext, "image/jpeg")

    if not image_bytes and not image_url:
        raise HTTPException(
            status_code=400,
            detail="Either an image file or image_url must be provided.",
        )

    try:
        result = await analyse_image(
            prompt=prompt,
            image_bytes=image_bytes,
            image_url=image_url,
            mime_type=mime_type,
        )
        return VisionResponse(description=result["description"], model=result["model"])
    except Exception as exc:
        logger.error("Vision error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Vision analysis failed: {exc}")


# ============================================================
# Entry Point
# ============================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level=settings.log_level.lower(),
    )
