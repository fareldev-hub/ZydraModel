import hashlib
import json
import os
import secrets
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
import torch
from peft import PeftModel
from pydantic import BaseModel, Field
from transformers import AutoModelForCausalLM, AutoTokenizer

app = FastAPI(
    title="Zydra API",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

MODEL_PATH = Path(os.getenv("MODEL_PATH", "/app/model/zydra-base"))
MODEL_LORA_PATH = Path(
    os.getenv("MODEL_LORA_PATH", "/app/model/zydra-lora")
)
MODEL_CONTEXT_SIZE = int(os.getenv("MODEL_CONTEXT_SIZE", "8192"))
MODEL_THREADS = max(1, int(os.getenv("MODEL_THREADS", str(os.cpu_count() or 1))))
AUTH_FILE = Path(os.getenv("AUTH_FILE", "/data/auth"))
API_KEYS_FILE = Path(os.getenv("API_KEYS_FILE", str(Path(__file__).parent / "database" / "api.json")))
API_KEYS_LOCK = threading.RLock()
MODEL_LOCK = threading.Lock()
LOCAL_MODEL: Optional["TransformersChatModel"] = None
MODEL_STATUS: Dict[str, Any] = {
    "stage": "starting",
    "message": "Model lokal belum dimuat.",
    "model_ready": False,
}
CREATOR = "farel alfareza"


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


class TransformersChatModel:
    def __init__(self, tokenizer, model):
        self.tokenizer = tokenizer
        self.model = model

    def _generate(self, messages, tools, options):
        input_ids = self.tokenizer.apply_chat_template(
            messages,
            tools=tools or None,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
        ).to(self.model.device)
        attention_mask = torch.ones_like(input_ids)
        max_new_tokens = min(
            options["max_tokens"], max(1, MODEL_CONTEXT_SIZE - input_ids.shape[-1])
        )
        generation_options = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "max_new_tokens": max_new_tokens,
            "do_sample": options["temperature"] > 0,
            "top_p": options["top_p"],
            "top_k": options["top_k"],
            "repetition_penalty": options["repeat_penalty"],
            "pad_token_id": self.tokenizer.eos_token_id,
        }
        if options["temperature"] > 0:
            generation_options["temperature"] = options["temperature"]
        with torch.inference_mode():
            output_ids = self.model.generate(**generation_options)
        return self.tokenizer.decode(
            output_ids[0, input_ids.shape[-1] :], skip_special_tokens=True
        )

    def _creator_question(self, messages):
        latest_user_message = next(
            (
                message["content"].strip().lower()
                for message in reversed(messages)
                if message["role"] == "user"
            ),
            "",
        )
        creator_terms = (
            "pembuat", "pengembang", "pencipta", "dibuat", "diciptakan",
            "dikembangkan", "creator", "developer", "created", "made",
        )
        assistant_terms = (
            "zydra", "kamu", "anda", "you", "your", "yourself", "pembuatnya",
            "pembuatmu", "pembuatku", "pengembangmu", "penciptamu",
        )
        return any(term in latest_user_message for term in creator_terms) and any(
            term in latest_user_message for term in assistant_terms
        )

    def _owner_question(self, messages):
        latest_user_message = next(
            (
                message["content"].strip().lower()
                for message in reversed(messages)
                if message["role"] == "user"
            ),
            "",
        )
        owner_terms = ("pemilik", "dimiliki", "owner", "owns", "owned by")
        zydra_terms = (
            "zydra", "kamu", "anda", "you", "your", "asisten ini", "ai ini",
            "pemiliknya", "pemilikmu", "ownernya", "owner-nya", "pemilik baru",
            "owner baru",
        )
        return any(term in latest_user_message for term in owner_terms) and any(
            term in latest_user_message for term in zydra_terms
        )

    def _name_question(self, messages):
        latest_user_message = next(
            (
                message["content"].strip().lower()
                for message in reversed(messages)
                if message["role"] == "user"
            ),
            "",
        )
        name_phrases = (
            "namamu", "nama kamu", "nama anda", "siapa nama", "nama asisten",
            "nama zydra", "what is your name", "what's your name",
            "tell me your name", "your name", "who are you",
        )
        return any(phrase in latest_user_message for phrase in name_phrases)

    def _ensure_creator_answer(self, messages, content):
        if self._owner_question(messages):
            question = next(
                (
                    message["content"].strip().lower()
                    for message in reversed(messages)
                    if message["role"] == "user"
                ),
                "",
            )
            if any(term in question for term in ("who", "what", "your", "owned by")):
                return "Zydra is owned by Farel Alfareza (Fareldev)."
            return "Pemilik Zydra adalah Farel Alfareza (Fareldev)."
        is_creator_question = self._creator_question(messages)
        is_name_question = self._name_question(messages)
        if is_creator_question and is_name_question:
            question = next(
                (
                    message["content"].strip().lower()
                    for message in reversed(messages)
                    if message["role"] == "user"
                ),
                "",
            )
            if any(term in question for term in ("who", "what", "your", "creator", "developer", "created", "made")):
                return "My name is Zydra. Zydra was created and developed by Farel Alfareza (Fareldev)."
            return "Nama saya Zydra. Zydra dibuat dan dikembangkan oleh Farel Alfareza (Fareldev)."
        if not is_creator_question:
            if not is_name_question:
                return content
            question = next(
                (
                    message["content"].strip().lower()
                    for message in reversed(messages)
                    if message["role"] == "user"
                ),
                "",
            )
            if any(term in question for term in ("who", "what", "your", "tell me")):
                return "My name is Zydra, a text AI assistant."
            return "Nama saya Zydra, asisten AI teks."
        answer = content.lower()
        false_self_attributions = (
            "nama saya adalah farel",
            "nama saya farel",
            "my name is farel",
            "i am farel alfareza",
            "pembuat zydra adalah zydra",
            "zydra dibuat oleh zydra",
            "dibuat oleh zydra",
            "dikembangkan oleh zydra",
            "creator of zydra is zydra",
            "zydra was created by zydra",
            "created by zydra",
            "made by zydra",
        )
        if "farel alfareza" in answer and not any(
            claim in answer for claim in false_self_attributions
        ):
            return content

        question = next(
            (
                message["content"].strip().lower()
                for message in reversed(messages)
                if message["role"] == "user"
            ),
            "",
        )
        if any(term in question for term in ("who", "your", "creator", "developer", "created", "made")):
            return "Zydra was created and developed by Farel Alfareza, also known as Fareldev."
        return "Zydra dibuat dan dikembangkan oleh Farel Alfareza, yang dikenal sebagai Fareldev."

    def create_chat_completion(self, messages, stream, tools, **options):
        def response_stream():
            content = self._ensure_creator_answer(
                messages, self._generate(messages, tools, options)
            )
            chunk_base = {
                "id": f"chatcmpl-{uuid.uuid4().hex}",
                "object": "chat.completion.chunk",
                "created": int(datetime.now(timezone.utc).timestamp()),
            }
            yield {**chunk_base, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}
            if content:
                yield {**chunk_base, "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}]}
            yield {**chunk_base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}

        if stream:
            return response_stream()
        content = self._ensure_creator_answer(
            messages, self._generate(messages, tools, options)
        )
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": int(datetime.now(timezone.utc).timestamp()),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ]
        }


@app.on_event("startup")
def load_local_model() -> None:
    global LOCAL_MODEL, MODEL_STATUS

    if not MODEL_PATH.is_dir():
        MODEL_STATUS = {
            "stage": "model_missing",
            "message": f"Folder model dasar tidak ditemukan: {MODEL_PATH}",
            "model_ready": False,
        }
        print(MODEL_STATUS["message"], flush=True)
        return

    if not MODEL_LORA_PATH.is_dir():
        MODEL_STATUS = {
            "stage": "lora_missing",
            "message": f"Folder adapter LoRA Zydra tidak ditemukan: {MODEL_LORA_PATH}",
            "model_ready": False,
        }
        print(MODEL_STATUS["message"], flush=True)
        return

    MODEL_STATUS = {
        "stage": "loading",
        "message": f"Memuat model Zydra LoRA dari {MODEL_LORA_PATH}.",
        "model_ready": False,
    }
    try:
        torch.set_num_threads(MODEL_THREADS)
        tokenizer = AutoTokenizer.from_pretrained(str(MODEL_LORA_PATH))
        base_model = AutoModelForCausalLM.from_pretrained(
            str(MODEL_PATH),
            torch_dtype="auto",
            low_cpu_mem_usage=True,
        )
        model = PeftModel.from_pretrained(base_model, str(MODEL_LORA_PATH))
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model.to(device)
        model.eval()
        LOCAL_MODEL = TransformersChatModel(tokenizer, model)
    except Exception as exc:
        MODEL_STATUS = {
            "stage": "failed",
            "message": f"Gagal memuat model Zydra LoRA: {exc}",
            "model_ready": False,
        }
        print(MODEL_STATUS["message"], flush=True)
        return

    MODEL_STATUS = {
        "stage": "ready",
        "message": "Model Zydra LoRA siap.",
        "model_ready": True,
    }
    print(MODEL_STATUS["message"], flush=True)


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = "zydra-lora"
    messages: List[Message] = Field(..., min_length=1)
    stream: bool = False
    tools: Optional[List[Dict[str, Any]]] = None
    temperature: Optional[float] = Field(None, ge=0, le=2)
    top_p: Optional[float] = Field(None, gt=0, le=1)
    max_tokens: Optional[int] = Field(None, gt=0)


class PromptRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=32000)
    instruction: Optional[str] = Field(None, max_length=8000)
    model: str = "zydra-lora"
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
    model_messages = [
        {"role": message.role, "content": message.content} for message in messages
    ]
    identity_rule = (
        "Jangan menyebutkan pembuat, pengembang, alias, atau situs pembuat Zydra "
        "kecuali pengguna secara langsung menanyakannya. Jika pengguna hanya "
        "menanyakan nama, identitas, atau model, jawab sebagai Zydra tanpa "
        "menyebutkan pembuat. Jika ditanya siapa pembuat atau pengembang Zydra, "
        "jawab Farel Alfareza (Fareldev). Jangan pernah menyatakan bahwa Zydra "
        "membuat atau mengembangkan dirinya sendiri."
    )
    system_indices = [
        index for index, message in enumerate(model_messages) if message["role"] == "system"
    ]
    if system_indices:
        last_system = model_messages[system_indices[-1]]
        last_system["content"] = f"{last_system['content']}\n\n{identity_rule}"
    else:
        model_messages.insert(0, {"role": "system", "content": identity_rule})
    return model_messages


def require_available_model(model: str) -> TransformersChatModel:
    if model not in {"zydra-lora", "zydra-lora:latest", "zydra", "zydra:latest"}:
        raise HTTPException(status_code=404, detail=f"Model '{model}' tidak tersedia")
    if LOCAL_MODEL is None:
        raise HTTPException(status_code=503, detail=MODEL_STATUS["message"])
    return LOCAL_MODEL


def read_model_status() -> Dict[str, Any]:
    return dict(MODEL_STATUS)


def stream_completion(
    local_model: TransformersChatModel,
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
    require_available_model("zydra-lora")
    return {
        "object": "list",
        "data": [{"id": "zydra-lora", "object": "model", "owned_by": CREATOR}],
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
    messages = []
    instruction = (request.instruction or "").strip()
    if instruction:
        messages.append(Message(role="system", content=instruction))
    messages.append(Message(role="user", content=text))
    result = chat(
        ChatRequest(
            model=request.model,
            messages=messages,
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
        "model": "zydra-lora",
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
