import base64
import binascii
import ipaddress
import json
import os
import secrets
import socket
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

import requests
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

app = FastAPI(title="Zydra API", version="1.0.0")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
AUTH = os.getenv("AUTH", "")
INSTRUCTIONS_FILE = Path(os.getenv("INSTRUCTIONS_FILE", "/data/instructions.txt"))
MODEL_STATUS_FILE = Path(os.getenv("MODEL_STATUS_FILE", "/tmp/zydra-setup-status.json"))
MAX_IMAGE_BYTES = 10 * 1024 * 1024
DEFAULT_INSTRUCTIONS = (
    "Anda adalah Zydra, asisten AI multimodal yang dikembangkan oleh Fareldev. "
    "Jawab dengan jelas, jujur, dan sopan. Gunakan Bahasa Indonesia jika pengguna "
    "menggunakan Bahasa Indonesia. Tolak permintaan yang berbahaya atau ilegal."
)


class ContentPart(BaseModel):
    type: str
    text: Optional[str] = None
    image_url: Optional[Dict[str, str]] = None


class Message(BaseModel):
    role: str
    content: Union[str, List[ContentPart]]


class ChatRequest(BaseModel):
    model: str = "zydra"
    messages: List[Message] = Field(..., min_length=1)
    stream: bool = False
    tools: Optional[List[Dict[str, Any]]] = None
    temperature: Optional[float] = Field(None, ge=0, le=2)
    top_p: Optional[float] = Field(None, gt=0, le=1)
    max_tokens: Optional[int] = Field(None, gt=0)


class InstructionUpdate(BaseModel):
    instructions: str = Field(..., min_length=1, max_length=20000)


def require_api_key(authorization: Optional[str], x_api_key: Optional[str]) -> None:
    if not AUTH:
        raise HTTPException(status_code=503, detail="AUTH belum dikonfigurasi")

    bearer_key = ""
    if authorization:
        scheme, _, credentials = authorization.partition(" ")
        if scheme.lower() == "bearer":
            bearer_key = credentials

    supplied_key = x_api_key or bearer_key
    if not secrets.compare_digest(supplied_key, AUTH):
        raise HTTPException(status_code=401, detail="API key tidak valid")


def read_instructions() -> str:
    try:
        return INSTRUCTIONS_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        return DEFAULT_INSTRUCTIONS
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Gagal membaca instruksi: {exc}")


def fetch_image_as_base64(url: str) -> str:
    parsed_url = urlparse(url)
    if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
        raise HTTPException(status_code=400, detail="URL gambar harus menggunakan HTTP atau HTTPS")
    if parsed_url.username or parsed_url.password:
        raise HTTPException(status_code=400, detail="URL gambar tidak boleh berisi kredensial")
    try:
        port = parsed_url.port
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Port URL gambar tidak valid: {exc}")
    hostname = parsed_url.hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="URL gambar harus memiliki hostname")
    if port and port != (443 if parsed_url.scheme == "https" else 80):
        raise HTTPException(status_code=400, detail="Port URL gambar tidak didukung")

    try:
        addresses = {
            ipaddress.ip_address(address[4][0])
            for address in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        }
    except (socket.gaierror, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Host URL gambar tidak valid: {exc}")
    if not addresses or any(not address.is_global for address in addresses):
        raise HTTPException(status_code=400, detail="URL gambar harus mengarah ke host publik")

    try:
        with requests.get(url, timeout=20, stream=True, allow_redirects=False) as response:
            if response.is_redirect:
                raise HTTPException(status_code=400, detail="Redirect URL gambar tidak didukung")
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
            if not content_type.startswith("image/"):
                raise HTTPException(status_code=400, detail="URL tidak mengarah ke file gambar")

            image_data = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                image_data.extend(chunk)
                if len(image_data) > MAX_IMAGE_BYTES:
                    raise HTTPException(status_code=413, detail="Ukuran gambar maksimal 10 MB")
            if not image_data:
                raise HTTPException(status_code=400, detail="File gambar kosong")
            return base64.b64encode(image_data).decode("ascii")
    except requests.RequestException as exc:
        raise HTTPException(status_code=400, detail=f"Gagal mengambil gambar: {exc}")


def image_part_to_base64(url: str) -> str:
    if url.startswith("data:"):
        try:
            header, encoded_data = url.split(",", 1)
            if not header.startswith("data:image/") or ";base64" not in header:
                raise ValueError("Format data URL gambar tidak didukung")
            image_data = base64.b64decode(encoded_data, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise HTTPException(status_code=400, detail=f"Data gambar tidak valid: {exc}")
        if len(image_data) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="Ukuran gambar maksimal 10 MB")
        if not image_data:
            raise HTTPException(status_code=400, detail="File gambar kosong")
        return base64.b64encode(image_data).decode("ascii")
    return fetch_image_as_base64(url)


def to_ollama_messages(messages: List[Message]) -> List[Dict[str, Any]]:
    ollama_messages: List[Dict[str, Any]] = [
        {"role": "system", "content": read_instructions()}
    ]
    for message in messages:
        if isinstance(message.content, str):
            ollama_messages.append({"role": message.role, "content": message.content})
            continue

        text_content = []
        images = []
        for part in message.content:
            if part.type == "text" and part.text:
                text_content.append(part.text)
            elif part.type == "image_url" and part.image_url:
                image_url = part.image_url.get("url", "")
                if not image_url:
                    raise HTTPException(status_code=400, detail="image_url harus memiliki url")
                images.append(image_part_to_base64(image_url))
            else:
                raise HTTPException(status_code=400, detail=f"Content type tidak didukung: {part.type}")

        ollama_message: Dict[str, Any] = {
            "role": message.role,
            "content": "\n".join(text_content),
        }
        if images:
            ollama_message["images"] = images
        ollama_messages.append(ollama_message)
    return ollama_messages


def ollama_error(exc: requests.RequestException) -> HTTPException:
    if isinstance(exc, requests.Timeout):
        return HTTPException(status_code=504, detail="Ollama timeout")

    response = getattr(exc, "response", None)
    if response is not None:
        try:
            response_data = response.json()
        except ValueError:
            response_data = {}
        upstream_detail = response_data.get("error") if isinstance(response_data, dict) else None
        if not upstream_detail:
            upstream_detail = response.text.strip()
        if not upstream_detail:
            upstream_detail = response.reason or "Unknown upstream error"
        return HTTPException(
            status_code=502,
            detail=f"Ollama HTTP {response.status_code}: {str(upstream_detail)[:2000]}",
        )

    return HTTPException(status_code=503, detail=f"Ollama tidak dapat memproses permintaan: {exc}")


def completion_chunk(
    completion_id: str,
    model: str,
    delta: Dict[str, Any],
    finish_reason: Optional[str],
) -> str:
    chunk = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


def format_tool_calls(tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    formatted_calls = []
    for call in tool_calls:
        function = call.get("function", {})
        arguments = function.get("arguments", {})
        formatted_calls.append({
            "id": call.get("id") or f"call_{uuid.uuid4().hex}",
            "type": "function",
            "function": {
                "name": function.get("name", ""),
                "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments),
            },
        })
    return formatted_calls


def available_ollama_models() -> List[str]:
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Ollama belum siap atau tidak dapat dijangkau: {exc}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"Respons daftar model Ollama tidak valid: {exc}")

    models = data.get("models")
    if not isinstance(models, list):
        raise HTTPException(status_code=502, detail="Respons daftar model Ollama tidak memiliki daftar models")
    return [item.get("name", "") for item in models if isinstance(item, dict)]


def require_available_model(model: str) -> None:
    model_names = available_ollama_models()
    if any(name == model or name.startswith(f"{model}:") for name in model_names):
        return
    if model == "zydra":
        setup_status = read_model_status(model_names)
        raise HTTPException(
            status_code=503,
            detail=setup_status["message"],
        )
    raise HTTPException(status_code=404, detail=f"Model '{model}' tidak tersedia di Ollama")


def read_model_status(model_names: Optional[List[str]] = None) -> Dict[str, Any]:
    try:
        setup_status = json.loads(MODEL_STATUS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        setup_status = {
            "stage": "starting",
            "message": "Status setup belum tersedia. Periksa log deploy Railway.",
        }
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=f"Gagal membaca status setup model: {exc}")

    if not isinstance(setup_status, dict):
        raise HTTPException(status_code=500, detail="Format status setup model tidak valid")

    if model_names is None:
        try:
            model_names = available_ollama_models()
        except HTTPException as exc:
            if setup_status.get("stage") != "failed":
                setup_status = {
                    "stage": "ollama_unavailable",
                    "message": exc.detail,
                }
            setup_status["model_ready"] = False
            return setup_status

    model_ready = any(name == "zydra" or name.startswith("zydra:") for name in model_names)
    if model_ready:
        setup_status = {"stage": "ready", "message": "Model Zydra siap."}
    elif setup_status.get("stage") == "ready":
        setup_status = {
            "stage": "model_missing",
            "message": "Setup selesai tetapi model Zydra tidak ada di penyimpanan Ollama.",
        }

    setup_status["model_ready"] = model_ready
    return setup_status


def stream_completion(payload: Dict[str, Any], model: str, completion_id: str):
    try:
        with requests.post(
            f"{OLLAMA_URL}/api/chat",
            json=payload,
            timeout=(10, 300),
            stream=True,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                if data.get("error"):
                    error = {
                        "error": {
                            "message": f"Ollama error: {str(data['error'])[:2000]}",
                            "type": "upstream_error",
                        }
                    }
                    yield f"data: {json.dumps(error, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"
                    return
                message = data.get("message", {})
                content = message.get("content", "")
                if content:
                    yield completion_chunk(completion_id, model, {"content": content}, None)
                if data.get("done"):
                    tool_calls = message.get("tool_calls", [])
                    if tool_calls:
                        delta = {
                            "tool_calls": [
                                {"index": index, **call}
                                for index, call in enumerate(format_tool_calls(tool_calls))
                            ]
                        }
                        yield completion_chunk(completion_id, model, delta, None)
                    yield completion_chunk(completion_id, model, {}, "tool_calls" if tool_calls else "stop")
                    yield "data: [DONE]\n\n"
                    return
    except requests.RequestException as exc:
        upstream_error = ollama_error(exc)
        error = {
            "error": {
                "message": upstream_error.detail,
                "type": "upstream_error",
                "code": upstream_error.status_code,
            }
        }
        yield f"data: {json.dumps(error, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    except ValueError as exc:
        error = {"error": {"message": f"Respons Ollama tidak valid: {exc}", "type": "upstream_error"}}
        yield f"data: {json.dumps(error, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"


@app.post("/v1/chat/completions")
def chat(
    req: ChatRequest,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
):
    require_api_key(authorization, x_api_key)
    require_available_model(req.model)
    ollama_messages = to_ollama_messages(req.messages)
    payload: Dict[str, Any] = {
        "model": req.model,
        "messages": ollama_messages,
        "stream": req.stream,
    }
    if req.tools:
        payload["tools"] = req.tools
    options: Dict[str, Any] = {}
    if req.temperature is not None:
        options["temperature"] = req.temperature
    if req.top_p is not None:
        options["top_p"] = req.top_p
    if req.max_tokens is not None:
        options["num_predict"] = req.max_tokens
    if options:
        payload["options"] = options

    if req.stream:
        completion_id = f"chatcmpl-{uuid.uuid4().hex}"
        return StreamingResponse(
            stream_completion(payload, req.model, completion_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    try:
        response = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=(10, 300))
        response.raise_for_status()
        result = response.json()
    except requests.RequestException as exc:
        raise ollama_error(exc)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"Respons Ollama tidak valid: {exc}")

    if result.get("error"):
        raise HTTPException(status_code=502, detail=f"Ollama error: {str(result['error'])[:2000]}")

    message = result.get("message", {})
    response_message: Dict[str, Any] = {
        "role": "assistant",
        "content": message.get("content", ""),
    }
    if message.get("tool_calls"):
        response_message["tool_calls"] = format_tool_calls(message["tool_calls"])

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "model": req.model,
        "choices": [{
            "index": 0,
            "message": response_message,
            "finish_reason": "tool_calls" if message.get("tool_calls") else "stop",
        }],
    }


@app.get("/v1/models")
def models(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
):
    require_api_key(authorization, x_api_key)
    model_names = available_ollama_models()
    return {
        "object": "list",
        "data": [
            {"id": name, "object": "model", "owned_by": "fareldev"}
            for name in model_names
        ],
    }


@app.get("/v1/instructions")
def get_instructions(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
):
    require_api_key(authorization, x_api_key)
    return {"instructions": read_instructions()}


@app.put("/v1/instructions")
def update_instructions(
    update: InstructionUpdate,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
):
    require_api_key(authorization, x_api_key)
    try:
        INSTRUCTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary_file = INSTRUCTIONS_FILE.with_name(
            f"{INSTRUCTIONS_FILE.name}.{uuid.uuid4().hex}.tmp"
        )
        temporary_file.write_text(update.instructions, encoding="utf-8")
        os.replace(temporary_file, INSTRUCTIONS_FILE)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Gagal menyimpan instruksi: {exc}")
    return {"instructions": update.instructions}


@app.get("/health")
def health():
    setup_status = read_model_status()
    return {
        "status": "ok",
        "model": "zydra",
        "model_ready": setup_status["model_ready"],
        "setup_stage": setup_status["stage"],
        "setup_message": setup_status["message"],
    }


@app.get("/status")
def model_status():
    return read_model_status()


@app.get("/ready")
def ready():
    health_status = health()
    if not health_status["model_ready"]:
        return JSONResponse(status_code=503, content=health_status)
    return health_status


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
