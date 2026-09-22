import asyncio
import json
import sqlite3

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.agent import run_agent
from src.config import MODEL, OLLAMA_URL, ROOT
from src.tools import StockTools, ToolError

app = FastAPI(title="Local Stock Lab", docs_url=None, redoc_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
app.mount("/static", StaticFiles(directory=ROOT / "assets"), name="static")
tools = StockTools()
agent_lock = asyncio.Lock()


@app.get("/")
def home():
    return FileResponse(ROOT / "assets/index.html")


@app.get("/api/status")
async def status():
    try:
        snapshot = tools.metadata()
    except (ToolError, sqlite3.Error, ValueError):
        snapshot = {"error": "本機快照尚未就緒。"}
    ollama = {"ready": False, "model": MODEL, "loaded": []}
    try:
        async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
            tags = (await client.get(f"{OLLAMA_URL}/api/tags")).json()
            ollama["ready"] = MODEL in [m["name"] for m in tags.get("models", [])]
            ps = (await client.get(f"{OLLAMA_URL}/api/ps")).json()
            ollama["loaded"] = [{"name": m["name"], "size": m.get("size"),
                                  "size_vram": m.get("size_vram")} for m in ps.get("models", [])]
    except (httpx.HTTPError, ValueError, KeyError):
        ollama["error"] = "Ollama 尚未啟動或模型尚未下載。"
    return {"snapshot": snapshot, "ollama": ollama, "busy": agent_lock.locked()}


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


@app.post("/api/chat")
async def chat(body: Question, request: Request):
    origin = request.headers.get("origin")
    if origin and origin != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "只接受同來源請求。")
    if not body.question.strip():
        raise HTTPException(422, "請輸入問題。")
    if agent_lock.locked():
        raise HTTPException(409, "已有問題執行中，請稍後。")
    await agent_lock.acquire()

    async def events():
        try:
            async with httpx.AsyncClient(timeout=180, trust_env=False) as client:
                async for event in run_agent(body.question.strip(), tools, client):
                    yield json.dumps(event, ensure_ascii=False) + "\n"
        except httpx.HTTPError:
            yield json.dumps({"type": "error", "text": "模型連線失敗或逾時。請確認 Ollama 已啟動並下載模型。"}, ensure_ascii=False) + "\n"
        except Exception:
            yield json.dumps({"type": "error", "text": "執行失敗，請檢查本機快照與服務狀態。"}, ensure_ascii=False) + "\n"
        finally:
            agent_lock.release()

    return StreamingResponse(events(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store"})
