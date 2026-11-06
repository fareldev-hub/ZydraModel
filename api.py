import hashlib
import json
import os
import secrets
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

app = FastAPI(title="Zydra API", version="1.0.0", docs_url=None, redoc_url=None)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
AUTH_FILE = Path(os.getenv("AUTH_FILE", "/data/auth"))
INSTRUCTIONS_FILE = Path(os.getenv("INSTRUCTIONS_FILE", "/data/instructions.txt"))
MODEL_STATUS_FILE = Path(os.getenv("MODEL_STATUS_FILE", "/tmp/zydra-setup-status.json"))
API_KEYS_FILE = Path(os.getenv("API_KEYS_FILE", str(Path(__file__).parent / "database" / "api.json")))
API_KEYS_LOCK = threading.RLock()
CREATOR = "farel alfareza"
DEFAULT_INSTRUCTIONS = (
    "Anda adalah Zydra, asisten AI teks yang dikembangkan oleh Fareldev. "
    "Jawab dengan jelas, jujur, dan sopan. Gunakan Bahasa Indonesia jika pengguna "
    "menggunakan Bahasa Indonesia. Tolak permintaan yang berbahaya atau ilegal."
)


@app.middleware("http")
async def add_creator_to_json_responses(request, call_next):
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if "application/json" not in content_type or response.status_code == 204:
        return response

    body = b"".join([chunk async for chunk in response.body_iterator])
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return response

    if isinstance(payload, dict):
        payload["creator"] = CREATOR
    else:
        payload = {"data": payload, "creator": CREATOR}
    headers = {
        name: value
        for name, value in response.headers.items()
        if name.lower() not in {"content-length", "content-type"}
    }
    return JSONResponse(
        content=payload,
        status_code=response.status_code,
        headers=headers,
        background=response.background,
    )


def load_or_create_auth() -> str:
    configured_auth = os.getenv("AUTH", "").strip()
    if configured_auth:
        return configured_auth

    try:
        AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
        auth = secrets.token_urlsafe(32)
        descriptor = os.open(AUTH_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as auth_file:
            auth_file.write(auth)
            auth_file.write("\n")
            auth_file.flush()
            os.fsync(auth_file.fileno())
        print(f"AUTH dibuat otomatis. Simpan password ini: {auth}", flush=True)
        return auth
    except FileExistsError:
        try:
            auth = AUTH_FILE.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise RuntimeError(f"Gagal membaca AUTH dari {AUTH_FILE}: {exc}") from exc
        if not auth:
            raise RuntimeError(f"File AUTH {AUTH_FILE} kosong; hapus file tersebut untuk membuat AUTH baru")
        return auth
    except OSError as exc:
        raise RuntimeError(f"Gagal membuat AUTH di {AUTH_FILE}: {exc}") from exc


AUTH = load_or_create_auth()


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = "zydra"
    messages: List[Message] = Field(..., min_length=1)
    stream: bool = False
    tools: Optional[List[Dict[str, Any]]] = None
    temperature: Optional[float] = Field(None, ge=0, le=2)
    top_p: Optional[float] = Field(None, gt=0, le=1)
    max_tokens: Optional[int] = Field(None, gt=0)


class PromptRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=32000)
    model: str = "zydra"
    temperature: Optional[float] = Field(None, ge=0, le=2)
    max_tokens: Optional[int] = Field(None, gt=0)


class InstructionUpdate(BaseModel):
    instructions: str = Field(..., min_length=1, max_length=20000)


class APIKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)


def supplied_api_key(authorization: Optional[str], x_api_key: Optional[str]) -> str:
    if x_api_key:
        return x_api_key
    if authorization:
        scheme, _, credentials = authorization.partition(" ")
        if scheme.lower() == "bearer":
            return credentials
    return ""


def read_api_key_records() -> List[Dict[str, Any]]:
    try:
        data = json.loads(API_KEYS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=f"Gagal membaca database API key: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("keys"), list):
        raise HTTPException(status_code=500, detail="Format database API key tidak valid")
    return data["keys"]


def write_api_key_records(records: List[Dict[str, Any]]) -> None:
    temporary_file = API_KEYS_FILE.with_name(f"{API_KEYS_FILE.name}.{uuid.uuid4().hex}.tmp")
    try:
        API_KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary_file.write_text(
            json.dumps({"keys": records}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary_file, 0o600)
        os.replace(temporary_file, API_KEYS_FILE)
    except OSError as exc:
        temporary_file.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Gagal menyimpan database API key: {exc}")


def require_admin_api_key(authorization: Optional[str], x_api_key: Optional[str]) -> None:
    if not AUTH:
        raise HTTPException(status_code=503, detail="AUTH belum dikonfigurasi")
    if not secrets.compare_digest(supplied_api_key(authorization, x_api_key), AUTH):
        raise HTTPException(status_code=401, detail="Endpoint pengelolaan API key memerlukan AUTH master")


def require_api_key(authorization: Optional[str], x_api_key: Optional[str]) -> None:
    if not AUTH:
        raise HTTPException(status_code=503, detail="AUTH belum dikonfigurasi")

    supplied_key = supplied_api_key(authorization, x_api_key)
    if secrets.compare_digest(supplied_key, AUTH):
        return
    if not supplied_key:
        raise HTTPException(status_code=401, detail="API key tidak valid")

    supplied_hash = hashlib.sha256(supplied_key.encode("utf-8")).hexdigest()
    with API_KEYS_LOCK:
        records = read_api_key_records()
    for record in records:
        stored_hash = record.get("key_hash") if isinstance(record, dict) else None
        if isinstance(stored_hash, str) and secrets.compare_digest(stored_hash, supplied_hash):
            return
    raise HTTPException(status_code=401, detail="API key tidak valid")


def read_instructions() -> str:
    try:
        return INSTRUCTIONS_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        return DEFAULT_INSTRUCTIONS
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Gagal membaca instruksi: {exc}")


def to_ollama_messages(messages: List[Message]) -> List[Dict[str, Any]]:
    ollama_messages: List[Dict[str, Any]] = [
        {"role": "system", "content": read_instructions()}
    ]
    for message in messages:
        ollama_messages.append({"role": message.role, "content": message.content})
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
        "creator": CREATOR,
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


def model_owner(model_name: str) -> str:
    model_family = model_name.split(":", 1)[0].lower()
    if model_family == "zydra":
        return CREATOR
    if model_family == "phi":
        return "Microsoft"
    return "Ollama"


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
            "message": "Status setup belum tersedia. Periksa log container.",
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
                        "creator": CREATOR,
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
            "creator": CREATOR,
            "error": {
                "message": upstream_error.detail,
                "type": "upstream_error",
                "code": upstream_error.status_code,
            }
        }
        yield f"data: {json.dumps(error, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    except ValueError as exc:
        error = {
            "creator": CREATOR,
            "error": {"message": f"Respons Ollama tidak valid: {exc}", "type": "upstream_error"},
        }
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
            {"id": name, "object": "model", "owned_by": model_owner(name)}
            for name in model_names
        ],
    }


@app.post("/v1/prompt")
def prompt(
    request: PromptRequest,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
):
    return generate_prompt_response(request, authorization, x_api_key)


def generate_prompt_response(
    request: PromptRequest,
    authorization: Optional[str] = None,
    x_api_key: Optional[str] = None,
):
    text = request.prompt.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Prompt tidak boleh kosong")
    result = chat(
        ChatRequest(
            model=request.model,
            messages=[Message(role="user", content=text)],
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        ),
        authorization=authorization,
        x_api_key=x_api_key,
    )
    return {
        "model": result["model"],
        "response": result["choices"][0]["message"]["content"],
    }


@app.get("/api/chat")
def get_api_chat(
    api: str = Query(..., min_length=1),
    prompt: str = Query(..., min_length=1, max_length=32000),
    model: str = "zydra",
):
    return generate_prompt_response(
        PromptRequest(prompt=prompt, model=model),
        x_api_key=api,
    )


@app.post("/api/chat")
def post_api_chat(
    request: PromptRequest,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
):
    return generate_prompt_response(request, authorization, x_api_key)


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


@app.get("/v1/api-keys")
def list_api_keys(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
):
    require_admin_api_key(authorization, x_api_key)
    with API_KEYS_LOCK:
        records = read_api_key_records()
    return {
        "data": [
            {
                "id": record["id"],
                "name": record["name"],
                "prefix": record["prefix"],
                "created_at": record["created_at"],
            }
            for record in records
            if isinstance(record, dict)
        ]
    }


@app.post("/v1/api-keys")
def create_api_key(
    request: APIKeyCreate,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
):
    require_admin_api_key(authorization, x_api_key)
    api_key = f"zdy-{secrets.token_urlsafe(32)}"
    record = {
        "id": uuid.uuid4().hex,
        "name": request.name.strip(),
        "prefix": f"{api_key[:12]}...",
        "key_hash": hashlib.sha256(api_key.encode("utf-8")).hexdigest(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if not record["name"]:
        raise HTTPException(status_code=422, detail="Nama API key tidak boleh kosong")
    with API_KEYS_LOCK:
        records = read_api_key_records()
        records.append(record)
        write_api_key_records(records)
    return {
        "api_key": api_key,
        "key": {key: record[key] for key in ("id", "name", "prefix", "created_at")},
        "message": "Simpan API key sekarang; nilainya tidak ditampilkan lagi.",
    }


@app.delete("/v1/api-keys/{key_id}")
def delete_api_key(
    key_id: str,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
):
    require_admin_api_key(authorization, x_api_key)
    with API_KEYS_LOCK:
        records = read_api_key_records()
        remaining_records = [record for record in records if record.get("id") != key_id]
        if len(remaining_records) == len(records):
            raise HTTPException(status_code=404, detail="API key tidak ditemukan")
        write_api_key_records(remaining_records)
    return {"deleted": True, "id": key_id}


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


@app.get("/", include_in_schema=False)
@app.get("/docs", include_in_schema=False)
def docs():
    return FileResponse(Path(__file__).parent / "static" / "docs.html")


app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
