"""
AI Provider Abstraction Layer
Supports: Google Gemini, Groq, Anthropic Claude
All providers return the same format so the chat router doesn't care which is used.
"""
import httpx
import json
from typing import AsyncGenerator, List, Dict
from config import settings


PROVIDERS = {
    "gemini": {
        "name": "Google Gemini",
        "models": [
            {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash", "badge": "Recommended • Free"},
            {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro", "badge": "Most Capable • Free"},
            {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash", "badge": "Fastest • Free"},
        ],
        "color": "#4285F4",
        "free": True,
    },
    "groq": {
        "name": "Groq",
        "models": [
            {"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B", "badge": "Fast • Free"},
            {"id": "mixtral-8x7b-32768", "name": "Mixtral 8x7B", "badge": "Free"},
            {"id": "gemma2-9b-it", "name": "Gemma 2 9B", "badge": "Lightweight • Free"},
        ],
        "color": "#F55036",
        "free": True,
    },
    "claude": {
        "name": "Anthropic Claude",
        "models": [
            {"id": "claude-sonnet-4-5", "name": "Claude Sonnet 4.5", "badge": "Recommended"},
            {"id": "claude-opus-4-5", "name": "Claude Opus 4.5", "badge": "Most Powerful"},
            {"id": "claude-haiku-4-5", "name": "Claude Haiku 4.5", "badge": "Fastest"},
        ],
        "color": "#D97706",
        "free": False,
    },
}

SYSTEM_PROMPT = """You are Tinku — a highly capable, friendly AI agent assistant.
You are helpful, concise, and intelligent. You adapt your tone to the user.
When doing math, be precise. When writing code, include comments.
When asked about sensitive topics, be careful and responsible.
Always be respectful and never generate harmful, offensive, or inappropriate content.
If asked to do something inappropriate, politely decline and explain why."""

INAPPROPRIATE_KEYWORDS = [
    "kill", "murder", "bomb", "weapon", "hack", "porn", "nude", "suicide",
    "drug synthesis", "make meth", "child abuse", "terrorist"
]


def check_content(text: str) -> tuple[bool, str]:
    """Basic content moderation. Returns (is_flagged, reason)."""
    lower = text.lower()
    for kw in INAPPROPRIATE_KEYWORDS:
        if kw in lower:
            return True, f"Contains potentially inappropriate content: '{kw}'"
    return False, ""


async def call_gemini(messages: List[Dict], model: str, api_key: str) -> AsyncGenerator[str, None]:
    """Call Google Gemini API."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    # Convert messages to Gemini format
    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})

    payload = {
        "contents": contents,
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 2048},
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code != 200:
            error = resp.json().get("error", {}).get("message", "Gemini API error")
            yield f"❌ Gemini Error: {error}"
            return
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        yield text


async def call_groq(messages: List[Dict], model: str, api_key: str) -> AsyncGenerator[str, None]:
    """Call Groq API (OpenAI-compatible)."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    formatted = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in messages:
        formatted.append({"role": msg["role"], "content": msg["content"]})

    payload = {"model": model, "messages": formatted, "max_tokens": 2048, "temperature": 0.7}

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code != 200:
            error = resp.json().get("error", {}).get("message", "Groq API error")
            yield f"❌ Groq Error: {error}"
            return
        data = resp.json()
        yield data["choices"][0]["message"]["content"]


async def call_claude(messages: List[Dict], model: str, api_key: str) -> AsyncGenerator[str, None]:
    """Call Anthropic Claude API."""
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json"
    }

    formatted = [{"role": msg["role"], "content": msg["content"]} for msg in messages]

    payload = {
        "model": model,
        "max_tokens": 2048,
        "system": SYSTEM_PROMPT,
        "messages": formatted,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code != 200:
            error = resp.json().get("error", {}).get("message", "Claude API error")
            yield f"❌ Claude Error: {error}"
            return
        data = resp.json()
        yield data["content"][0]["text"]


async def generate_response(
    messages: List[Dict],
    provider: str,
    model: str,
    api_key: str
) -> AsyncGenerator[str, None]:
    """Route to correct provider."""
    if provider == "gemini":
        async for chunk in call_gemini(messages, model, api_key):
            yield chunk
    elif provider == "groq":
        async for chunk in call_groq(messages, model, api_key):
            yield chunk
    elif provider == "claude":
        async for chunk in call_claude(messages, model, api_key):
            yield chunk
    else:
        yield f"❌ Unknown provider: {provider}"
