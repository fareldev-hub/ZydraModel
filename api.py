import hashlib
import json
import os
import re
import secrets
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from llama_cpp import Llama
from pydantic import BaseModel, Field

app = FastAPI(
    title="Zydra API",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

MODEL_PATH = Path(os.getenv("MODEL_PATH", "/app/model/qwen2.5-0.5b-instruct-q4_k_m.gguf"))
MODEL_LORA_PATH = os.getenv("MODEL_LORA_PATH")
MODEL_CONTEXT_SIZE = int(os.getenv("MODEL_CONTEXT_SIZE", "8192"))
MODEL_THREADS = max(1, int(os.getenv("MODEL_THREADS", str(os.cpu_count() or 1))))
AUTH_FILE = Path(os.getenv("AUTH_FILE", "/data/auth"))
IDENTITY_INSTRUCTIONS_FILE = Path(
    os.getenv(
        "IDENTITY_INSTRUCTIONS_FILE",
        str(Path(__file__).parent / "training" / "data.txt"),
    )
)
API_KEYS_FILE = Path(os.getenv("API_KEYS_FILE", str(Path(__file__).parent / "database" / "api.json")))
API_KEYS_LOCK = threading.RLock()
MODEL_LOCK = threading.Lock()
LOCAL_MODEL: Optional[Llama] = None
MODEL_STATUS: Dict[str, Any] = {
    "stage": "starting",
    "message": "Model lokal belum dimuat.",
    "model_ready": False,
}
CREATOR = "farel alfareza"


def load_identity_instructions() -> str:
    try:
        instructions = IDENTITY_INSTRUCTIONS_FILE.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(
            f"Cannot read identity instructions from {IDENTITY_INSTRUCTIONS_FILE}: {exc}"
        ) from exc
    if not instructions:
        raise RuntimeError(f"Identity instructions are empty in {IDENTITY_INSTRUCTIONS_FILE}")
    return instructions


def load_identity_profile(instructions: str) -> Dict[str, str]:
    profile: Dict[str, str] = {}
    for line in instructions.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            normalized_key = key.strip().lower()
            if normalized_key in {
                "nama asisten",
                "jenis asisten",
                "pembuat",
                "alias pembuat",
                "situs pembuat",
                "model dasar",
            }:
                profile[normalized_key] = value.strip()

    required_keys = {
        "nama asisten",
        "jenis asisten",
        "pembuat",
        "alias pembuat",
        "situs pembuat",
    }
    missing_keys = required_keys - profile.keys()
    if missing_keys:
        raise RuntimeError(
            f"Missing identity fields in {IDENTITY_INSTRUCTIONS_FILE}: "
            f"{', '.join(sorted(missing_keys))}"
        )
    return profile


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


@app.on_event("startup")
def load_local_model() -> None:
    global LOCAL_MODEL, MODEL_STATUS

    if not MODEL_PATH.is_file():
        MODEL_STATUS = {
            "stage": "model_missing",
            "message": f"File model GGUF tidak ditemukan: {MODEL_PATH}",
            "model_ready": False,
        }
        print(MODEL_STATUS["message"], flush=True)
        return

    if MODEL_LORA_PATH and not Path(MODEL_LORA_PATH).is_file():
        MODEL_STATUS = {
            "stage": "lora_missing",
            "message": f"File adapter LoRA GGUF tidak ditemukan: {MODEL_LORA_PATH}",
            "model_ready": False,
        }
        print(MODEL_STATUS["message"], flush=True)
        return

    MODEL_STATUS = {
        "stage": "loading",
        "message": f"Memuat model lokal dari {MODEL_PATH}."
        + (f" Adapter LoRA: {MODEL_LORA_PATH}." if MODEL_LORA_PATH else ""),
        "model_ready": False,
    }
    try:
        LOCAL_MODEL = Llama(
            model_path=str(MODEL_PATH),
            lora_path=MODEL_LORA_PATH,
            n_ctx=MODEL_CONTEXT_SIZE,
            n_threads=MODEL_THREADS,
            verbose=False,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        MODEL_STATUS = {
            "stage": "failed",
            "message": f"Gagal memuat model GGUF dari {MODEL_PATH}: {exc}",
            "model_ready": False,
        }
        raise RuntimeError(MODEL_STATUS["message"]) from exc

    MODEL_STATUS = {
        "stage": "ready",
        "message": "Model Zydra lokal siap.",
        "model_ready": True,
    }
    print(MODEL_STATUS["message"], flush=True)


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


class APIKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)


def supplied_api_key(
    authorization: Optional[str],
    x_api_key: Optional[str],
    query_api_key: Optional[str] = None,
) -> str:
    if x_api_key:
        return x_api_key
    if authorization:
        scheme, _, credentials = authorization.partition(" ")
        if scheme.lower() == "bearer":
            return credentials
    if query_api_key:
        return query_api_key
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


def require_admin_api_key(
    authorization: Optional[str],
    x_api_key: Optional[str],
    query_api_key: Optional[str] = None,
) -> None:
    if not AUTH:
        raise HTTPException(status_code=503, detail="AUTH belum dikonfigurasi")
    if not secrets.compare_digest(
        supplied_api_key(authorization, x_api_key, query_api_key), AUTH
    ):
        raise HTTPException(status_code=401, detail="Endpoint pengelolaan API key memerlukan AUTH master")


def require_api_key(
    authorization: Optional[str],
    x_api_key: Optional[str],
    query_api_key: Optional[str] = None,
) -> None:
    if not AUTH:
        raise HTTPException(status_code=503, detail="AUTH belum dikonfigurasi")

    supplied_key = supplied_api_key(authorization, x_api_key, query_api_key)
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


def to_model_messages(messages: List[Message]) -> List[Dict[str, Any]]:
    return [
        {"role": message.role, "content": message.content} for message in messages
    ]


def identity_response(
    messages: List[Message], identity_profile: Dict[str, str]
) -> Optional[str]:
    latest_user_message = next(
        (message.content.strip().lower() for message in reversed(messages) if message.role == "user"),
        "",
    )
    if not latest_user_message:
        return None

    asks_about_creator = bool(
        re.search(r"\b(siapa|who)\b", latest_user_message)
        and re.search(
            r"\b(pembuat(?:ku|mu)?|pengembang(?:ku|mu)?|membuat|bikin|menciptakan|"
            r"creator|developer|made|created|developed)\b",
            latest_user_message,
        )
        and re.search(
            r"\b(kamu|anda|you|your|zydra)\b|"
            r"\b(pembuatku|pembuatmu|pengembangku|pengembangmu)\b",
            latest_user_message,
        )
    )
    if asks_about_creator:
        return (
            f"Saya {identity_profile['nama asisten']}, "
            f"{identity_profile['jenis asisten']} yang dibuat dan dikembangkan "
            f"oleh {identity_profile['pembuat']} ("
            f"{identity_profile['alias pembuat']}). Situs pembuat: "
            f"{identity_profile['situs pembuat']}."
        )

    asks_about_other_model = bool(
        re.search(
            r"\b(apakah|apa)\b.*\b(kamu|anda)\b.*\b(qwen|alibaba|gemini|google|deepmind)\b",
            latest_user_message,
        )
        or re.search(
            r"\b(are you|r u)\b.*\b(qwen|alibaba|gemini|google|deepmind)\b",
            latest_user_message,
        )
    )
    if asks_about_other_model:
        return (
            f"Saya {identity_profile['nama asisten']}, "
            f"{identity_profile['jenis asisten']} yang dibuat oleh "
            f"{identity_profile['pembuat']} "
            f"({identity_profile['alias pembuat']})."
        )

    asks_about_identity = bool(
        re.search(r"\b(siapa|who)\b.*\b(kamu|anda|namamu|you|your name)\b", latest_user_message)
        or re.search(
            r"\b(nama|name)\b.*\b(kamu|anda|mu|namamu|you|zydra)\b",
            latest_user_message,
        )
        or re.search(r"\b(apa namamu|what is your name|what's your name)\b", latest_user_message)
        or re.search(
            r"\b(kamu(?: ini)? siapa|siapa kamu|siapa anda|anda(?: ini)? siapa|"
            r"who are you|what are you|introduce yourself|tell me about yourself|"
            r"perkenalkan diri(?:mu)?|what model are you|what model|model apa|"
            r"model apakah|siapa zydra|what is zydra|nama ai ini|nama model ini)\b",
            latest_user_message,
        )
    )
    if asks_about_identity:
        return (
            f"Saya {identity_profile['nama asisten']}, "
            f"{identity_profile['jenis asisten']} yang dibuat oleh "
            f"{identity_profile['pembuat']} "
            f"({identity_profile['alias pembuat']})."
        )
    return None


def identity_stream(
    content: str, model: str, completion_id: str
) -> Iterator[str]:
    created = int(datetime.now(timezone.utc).timestamp())
    base = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
    }
    for choice in (
        {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None},
        {"index": 0, "delta": {"content": content}, "finish_reason": None},
        {"index": 0, "delta": {}, "finish_reason": "stop"},
    ):
        yield f"data: {json.dumps({**base, 'choices': [choice]}, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


def require_available_model(model: str) -> Llama:
    if model not in {"zydra", "zydra:latest"}:
        raise HTTPException(status_code=404, detail=f"Model '{model}' tidak tersedia")
    if LOCAL_MODEL is None:
        raise HTTPException(status_code=503, detail=MODEL_STATUS["message"])
    return LOCAL_MODEL


def read_model_status() -> Dict[str, Any]:
    return dict(MODEL_STATUS)


def stream_completion(
    local_model: Llama,
    messages: List[Dict[str, Any]],
    model: str,
    completion_id: str,
    options: Dict[str, Any],
    tools: Optional[List[Dict[str, Any]]],
):
    try:
        with MODEL_LOCK:
            response_stream = local_model.create_chat_completion(
                messages=messages,
                stream=True,
                tools=tools,
                **options,
            )
            for chunk in response_stream:
                chunk["id"] = completion_id
                chunk["model"] = model
                chunk["creator"] = CREATOR
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        error = {
            "creator": CREATOR,
            "error": {
                "message": f"Gagal menghasilkan respons dari model lokal: {exc}",
                "type": "model_error",
            },
        }
        yield f"data: {json.dumps(error, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"


@app.post("/v1/chat/completions")
def chat(
    req: ChatRequest,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
    query_api_key: Optional[str] = Query(None, alias="apikey"),
):
    require_api_key(authorization, x_api_key, query_api_key)
    identity_instructions = load_identity_instructions()
    identity_profile = load_identity_profile(identity_instructions)
    direct_identity_response = identity_response(req.messages, identity_profile)
    if direct_identity_response is not None:
        if req.stream:
            return StreamingResponse(
                identity_stream(
                    direct_identity_response,
                    req.model,
                    f"chatcmpl-{uuid.uuid4().hex}",
                ),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": int(datetime.now(timezone.utc).timestamp()),
            "model": req.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": direct_identity_response},
                    "finish_reason": "stop",
                }
            ],
        }

    local_model = require_available_model(req.model)
    messages = to_model_messages(req.messages)
    options: Dict[str, Any] = {
        "temperature": req.temperature if req.temperature is not None else 0.7,
        "top_p": req.top_p if req.top_p is not None else 0.9,
        "top_k": 40,
        "repeat_penalty": 1.1,
        "max_tokens": req.max_tokens if req.max_tokens is not None else 1024,
    }

    if req.stream:
        completion_id = f"chatcmpl-{uuid.uuid4().hex}"
        return StreamingResponse(
            stream_completion(
                local_model,
                messages,
                req.model,
                completion_id,
                options,
                req.tools,
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    try:
        with MODEL_LOCK:
            result = local_model.create_chat_completion(
                messages=messages,
                stream=False,
                tools=req.tools,
                **options,
            )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Gagal menghasilkan respons dari model lokal: {exc}",
        ) from exc

    result["model"] = req.model
    return result


@app.get("/v1/models")
def models(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
    query_api_key: Optional[str] = Query(None, alias="apikey"),
):
    require_api_key(authorization, x_api_key, query_api_key)
    require_available_model("zydra")
    return {
        "object": "list",
        "data": [{"id": "zydra", "object": "model", "owned_by": CREATOR}],
    }


@app.post("/v1/prompt")
def prompt(
    request: PromptRequest,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
    query_api_key: Optional[str] = Query(None, alias="apikey"),
):
    require_api_key(authorization, x_api_key, query_api_key)
    return generate_prompt_response(request, authorization, x_api_key, query_api_key)


@app.get("/v1/prompt")
def prompt_get(
    prompt_text: str = Query(..., alias="prompt", min_length=1, max_length=32000),
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
    query_api_key: Optional[str] = Query(None, alias="apikey"),
):
    require_api_key(authorization, x_api_key, query_api_key)
    return generate_prompt_response(
        PromptRequest(prompt=prompt_text),
        authorization,
        x_api_key,
        query_api_key,
    )


def generate_prompt_response(
    request: PromptRequest,
    authorization: Optional[str] = None,
    x_api_key: Optional[str] = None,
    query_api_key: Optional[str] = None,
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
        query_api_key=query_api_key,
    )
    return {
        "model": result["model"],
        "response": result["choices"][0]["message"]["content"],
    }


@app.get("/v1/api-keys")
def list_api_keys(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
    query_api_key: Optional[str] = Query(None, alias="apikey"),
):
    require_admin_api_key(authorization, x_api_key, query_api_key)
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
    query_api_key: Optional[str] = Query(None, alias="apikey"),
):
    require_admin_api_key(authorization, x_api_key, query_api_key)
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
    query_api_key: Optional[str] = Query(None, alias="apikey"),
):
    require_admin_api_key(authorization, x_api_key, query_api_key)
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
def home():
    return FileResponse(Path(__file__).parent / "static" / "index.html")
