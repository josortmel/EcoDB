import os
import re
import httpx
from datetime import datetime
from fastapi import FastAPI, Request

app = FastAPI()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ECODB_API_URL = os.environ.get("ECODB_API_URL", "http://api:8080")
ECODB_API_KEY = os.environ.get("ECODB_API_KEY", "")

_EXPECTED_PATTERN = re.compile(r"Container /(\S+).*(?:Restarting|Failed)")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request):
    body = await request.json()
    text = body.get("text", "")
    timestamp = datetime.now().isoformat()
    container = _extract_container(text)
    status = _classify(text)

    await _send_telegram(text, timestamp, container, status)
    await _save_to_ecodb(text, timestamp, container, status)

    return {"received": True, "container": container, "status": status, "timestamp": timestamp}


def _extract_container(text: str) -> str:
    match = re.search(r"Container /(\S+)", text)
    return match.group(1) if match else "unknown"


def _classify(text: str) -> str:
    if not text or not _EXPECTED_PATTERN.search(text):
        return "unrecognized"
    if "Failed" in text:
        return "failed"
    return "restarted"


async def _send_telegram(text: str, timestamp: str, container: str, status: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    icons = {"restarted": "⚠️", "failed": "❌", "unrecognized": "❓"}
    icon = icons.get(status, "❓")
    if status == "unrecognized":
        preview = text[:200] if text else "(empty)"
        message = f"{icon} EcoDB alerting [{timestamp}]\nWebhook recibido con payload no reconocido: {preview}"
    else:
        message = f"{icon} EcoDB alerting [{timestamp}]\n{text}"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message})


async def _save_to_ecodb(text: str, timestamp: str, container: str, status: str):
    if not ECODB_API_KEY:
        return
    if status == "failed":
        content = f"ALERTA AUTOHEAL [{timestamp}]: {text} — REINICIO FALLIDO, requiere intervencion manual."
    elif status == "unrecognized":
        preview = text[:200] if text else "(empty)"
        content = f"ALERTA AUTOHEAL [{timestamp}]: webhook recibido con payload no reconocido: {preview}"
    else:
        content = f"ALERTA AUTOHEAL [{timestamp}]: {text}"
    async with httpx.AsyncClient(timeout=15) as client:
        await client.post(
            f"{ECODB_API_URL}/memories",
            headers={"Authorization": f"Bearer {ECODB_API_KEY}"},
            json={
                "content": content,
                "type": "tecnico",
                "agent_identifier": "SIN_AUTOR",
                "tags": ["alerting", "autoheal", container, status],
            },
        )
