import base64
import os
import requests
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Union

app = FastAPI()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
API_KEY = "fareldev_zydra_model_key"
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

class ContentPart(BaseModel):
    type: str
    text: Optional[str] = None
    image_url: Optional[Dict[str, str]] = None

class Message(BaseModel):
    role: str
    content: Union[str, List[ContentPart]]

class ChatRequest(BaseModel):
    model: str = "zydra"
    messages: List[Message]
    stream: bool = False
    tools: Optional[List[Dict[str, Any]]] = None

def fetch_image_as_base64(url: str) -> str:
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        img_data = base64.b64encode(response.content).decode("utf-8")
        return img_data
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Gagal mengambil gambar: {str(e)}")

def web_search(query: str, max_results: int = 5) -> str:
    if not SERPER_API_KEY:
        return "Error: SERPER_API_KEY tidak dikonfigurasi"
    try:
        response = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": query, "num": max_results},
            timeout=15
        )
        response.raise_for_status()
        data = response.json()
        results = []
        for item in data.get("organic", [])[:max_results]:
            results.append(f"Judul: {item.get('title')}\nURL: {item.get('link')}\nSnippet: {item.get('snippet')}")
        return "\n\n".join(results) if results else "Tidak ada hasil ditemukan"
    except Exception as e:
        return f"Error saat pencarian: {str(e)}"

@app.post("/v1/chat/completions")
async def chat(req: ChatRequest, authorization: str = Header(None)):
    if authorization != f"Bearer {API_KEY}":
        raise HTTPException(status_code=401, detail="API key tidak valid")

    ollama_messages = []
    for msg in req.messages:
        if isinstance(msg.content, str):
            ollama_messages.append({"role": msg.role, "content": msg.content})
        else:
            text_content = ""
            images = []
            for part in msg.content:
                if part.type == "text" and part.text:
                    text_content += part.text
                elif part.type == "image_url" and part.image_url:
                    url = part.image_url.get("url", "")
                    if url.startswith("data:image"):
                        base64_data = url.split(",", 1)[1]
                        images.append(base64_data)
                    else:
                        images.append(fetch_image_as_base64(url))
            ollama_msg = {"role": msg.role, "content": text_content}
            if images:
                ollama_msg["images"] = images
            ollama_messages.append(ollama_msg)

    tools_definition = [
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Mencari informasi terbaru di internet. Gunakan ini ketika pengguna bertanya tentang berita terkini, fakta real-time, atau hal yang membutuhkan data terbaru.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Query pencarian yang spesifik dan jelas"
                        }
                    },
                    "required": ["query"]
                }
            }
        }
    ]

    payload = {
        "model": req.model,
        "messages": ollama_messages,
        "stream": False,
        "tools": tools_definition
    }

    try:
        response = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=120)
        response.raise_for_status()
        result = response.json()
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Ollama timeout")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ollama error: {str(e)}")

    message = result.get("message", {})

    if message.get("tool_calls"):
        for tool_call in message["tool_calls"]:
            if tool_call["function"]["name"] == "web_search":
                query = tool_call["function"]["arguments"].get("query", "")
                search_result = web_search(query)
                ollama_messages.append(message)
                ollama_messages.append({
                    "role": "tool",
                    "content": search_result,
                    "tool_name": "web_search"
                })
                second_payload = {
                    "model": req.model,
                    "messages": ollama_messages,
                    "stream": False
                }
                second_response = requests.post(f"{OLLAMA_URL}/api/chat", json=second_payload, timeout=120)
                second_response.raise_for_status()
                result = second_response.json()

    return {
        "id": "chatcmpl-zydra",
        "object": "chat.completion",
        "model": "zydra",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": result.get("message", {}).get("content", "")
            },
            "finish_reason": "stop"
        }]
    }

@app.get("/health")
def health():
    return {"status": "ok", "model": "zydra"}
