"""
AI Provider Abstraction Layer — Tinku Agent v3
Supports: Google Gemini, Groq, Anthropic Claude
NEW: Web Search, Live Weather, Currency, ReAct reasoning
"""
import httpx
import json
import re
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
        "color": "#4285F4", "free": True,
    },
    "groq": {
        "name": "Groq",
        "models": [
            {"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B", "badge": "Fast • Free"},
            {"id": "mixtral-8x7b-32768", "name": "Mixtral 8x7B", "badge": "Free"},
            {"id": "gemma2-9b-it", "name": "Gemma 2 9B", "badge": "Lightweight • Free"},
        ],
        "color": "#F55036", "free": True,
    },
    "claude": {
        "name": "Anthropic Claude",
        "models": [
            {"id": "claude-sonnet-4-5", "name": "Claude Sonnet 4.5", "badge": "Recommended"},
            {"id": "claude-opus-4-5", "name": "Claude Opus 4.5", "badge": "Most Powerful"},
            {"id": "claude-haiku-4-5", "name": "Claude Haiku 4.5", "badge": "Fastest"},
        ],
        "color": "#D97706", "free": False,
    },
}

SYSTEM_PROMPT = """You are Tinku — a highly capable, friendly AI agent assistant.
You are helpful, concise, and intelligent. You adapt your tone to the user.
When doing math, be precise. When writing code, include comments.
When asked about sensitive topics, be careful and responsible.
Always be respectful and never generate harmful content.
When you receive tool results (weather data, search results etc), use them to give
accurate, helpful answers. Present data in a clean, readable format with emojis."""

INAPPROPRIATE_KEYWORDS = [
    "kill", "murder", "bomb", "weapon", "hack", "porn", "nude", "suicide",
    "drug synthesis", "make meth", "child abuse", "terrorist"
]

# ═══════════════════════════════════════
# TOOL DETECTION
# ═══════════════════════════════════════

WEATHER_KEYWORDS = ["weather", "temperature", "forecast", "rain", "sunny", "humid",
    "climate", "hot", "cold", "wind", "storm", "umbrella", "celsius", "heat"]

SEARCH_KEYWORDS = ["latest", "news", "today", "current", "recent", "2024", "2025",
    "who is", "what happened", "trending", "update", "now", "live", "price of",
    "stock", "score", "result", "election", "breaking"]

CURRENCY_KEYWORDS = ["convert", "exchange rate", "usd", "inr", "eur", "gbp",
    "rupee", "dollar", "euro", "pound", "currency", "forex"]

CITY_NAMES = ["mumbai", "delhi", "bangalore", "bengaluru", "chennai", "kolkata",
    "hyderabad", "pune", "ahmedabad", "jaipur", "london", "new york", "paris",
    "tokyo", "dubai", "singapore", "sydney", "toronto", "berlin", "beijing"]

CITY_COORDS = {
    "Mumbai": (19.0760, 72.8777), "Delhi": (28.6139, 77.2090),
    "Bangalore": (12.9716, 77.5946), "Bengaluru": (12.9716, 77.5946),
    "Chennai": (13.0827, 80.2707), "Kolkata": (22.5726, 88.3639),
    "Hyderabad": (17.3850, 78.4867), "Pune": (18.5204, 73.8567),
    "Ahmedabad": (23.0225, 72.5714), "Jaipur": (26.9124, 75.7873),
    "London": (51.5074, -0.1278), "New York": (40.7128, -74.0060),
    "Paris": (48.8566, 2.3522), "Tokyo": (35.6762, 139.6503),
    "Dubai": (25.2048, 55.2708), "Singapore": (1.3521, 103.8198),
    "Sydney": (-33.8688, 151.2093), "Toronto": (43.6532, -79.3832),
    "Berlin": (52.5200, 13.4050), "Beijing": (39.9042, 116.4074),
}

WMO_CODES = {
    0: "☀️ Clear sky", 1: "🌤 Mainly clear", 2: "⛅ Partly cloudy",
    3: "☁️ Overcast", 45: "🌫 Foggy", 51: "🌦 Light drizzle",
    61: "🌧 Light rain", 63: "🌧 Rain", 65: "🌧 Heavy rain",
    71: "🌨 Light snow", 73: "❄️ Snow", 80: "🌦 Showers",
    95: "⛈ Thunderstorm",
}


def detect_tools_needed(message: str) -> dict:
    """Detect which tools are needed for this message."""
    lower = message.lower()
    tools = {"weather": False, "search": False, "currency": False, "city": None}

    if any(kw in lower for kw in WEATHER_KEYWORDS):
        tools["weather"] = True
        for city in CITY_NAMES:
            if city in lower:
                tools["city"] = city.title()
                break
        if not tools["city"]:
            tools["city"] = "Mumbai"

    if any(kw in lower for kw in SEARCH_KEYWORDS):
        tools["search"] = True

    if any(kw in lower for kw in CURRENCY_KEYWORDS):
        tools["currency"] = True

    return tools


# ═══════════════════════════════════════
# TOOL: LIVE WEATHER
# ═══════════════════════════════════════

async def get_weather(city: str) -> str:
    """Fetch live weather from Open-Meteo (free, no API key!)."""
    try:
        coords = CITY_COORDS.get(city, CITY_COORDS["Mumbai"])
        lat, lon = coords
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
            f"precipitation_probability,weather_code,wind_speed_10m,uv_index"
            f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
            f"&timezone=auto&forecast_days=3"
        )
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            data = resp.json()

        c = data["current"]
        d = data["daily"]
        condition = WMO_CODES.get(c["weather_code"], "🌡 Unknown")

        return f"""🌍 **Live Weather — {city}**

{condition}
🌡️ **{c['temperature_2m']}°C** (Feels like {c['apparent_temperature']}°C)
💧 Humidity: {c['relative_humidity_2m']}%
🌧 Rain chance: {c['precipitation_probability']}%
💨 Wind: {c['wind_speed_10m']} km/h | ☀️ UV: {c['uv_index']}

**3-Day Forecast:**
📅 Today: {d['temperature_2m_min'][0]}°C – {d['temperature_2m_max'][0]}°C | 🌧 {d['precipitation_probability_max'][0]}%
📅 Tomorrow: {d['temperature_2m_min'][1]}°C – {d['temperature_2m_max'][1]}°C | 🌧 {d['precipitation_probability_max'][1]}%
📅 Day 3: {d['temperature_2m_min'][2]}°C – {d['temperature_2m_max'][2]}°C | 🌧 {d['precipitation_probability_max'][2]}%"""
    except Exception as e:
        return f"⚠️ Weather fetch failed: {str(e)}"


# ═══════════════════════════════════════
# TOOL: WEB SEARCH
# ═══════════════════════════════════════

async def web_search(query: str) -> str:
    """Search using DuckDuckGo Instant Answer API (free, no key!)."""
    try:
        url = "https://api.duckduckgo.com/"
        params = {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
            data = resp.json()

        results = []
        if data.get("Abstract"):
            results.append(f"📖 **{data.get('Heading', 'Answer')}:**\n{data['Abstract']}")
            if data.get("AbstractURL"):
                results.append(f"🔗 Source: {data['AbstractURL']}")
        if data.get("Answer"):
            results.append(f"✅ **Quick Answer:** {data['Answer']}")

        topics = data.get("RelatedTopics", [])[:3]
        if topics:
            results.append("\n📰 **Related:**")
            for t in topics:
                if isinstance(t, dict) and t.get("Text"):
                    results.append(f"• {t['Text'][:150]}")

        if results:
            return "🔍 **Web Search Results:**\n\n" + "\n".join(results)
        return f"🔍 Searched for: '{query}'\n\nNo instant results. Using training knowledge:"
    except Exception as e:
        return f"🔍 Search attempted but failed. Using training knowledge:"


# ═══════════════════════════════════════
# TOOL: CURRENCY
# ═══════════════════════════════════════

async def get_exchange_rate() -> str:
    """Get live exchange rates (free API)."""
    try:
        url = "https://open.er-api.com/v6/latest/USD"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            data = resp.json()
        rates = data.get("rates", {})
        return f"""💱 **Live Exchange Rates (Base: USD)**

🇮🇳 1 USD = ₹{rates.get('INR', 83.5):.2f} INR
🇪🇺 1 USD = €{rates.get('EUR', 0.92):.4f} EUR
🇬🇧 1 USD = £{rates.get('GBP', 0.79):.4f} GBP
🇯🇵 1 USD = ¥{rates.get('JPY', 149.5):.2f} JPY
🇦🇪 1 USD = {rates.get('AED', 3.67):.2f} AED
🇸🇬 1 USD = S${rates.get('SGD', 1.34):.4f} SGD

*Updated: {data.get('time_last_update_utc', 'Recently')}*"""
    except:
        return "💱 Exchange rates temporarily unavailable."


# ═══════════════════════════════════════
# CONTENT MODERATION
# ═══════════════════════════════════════

def check_content(text: str) -> tuple[bool, str]:
    lower = text.lower()
    for kw in INAPPROPRIATE_KEYWORDS:
        if kw in lower:
            return True, f"Contains potentially inappropriate content: '{kw}'"
    return False, ""


# ═══════════════════════════════════════
# AI PROVIDERS
# ═══════════════════════════════════════

async def call_gemini(messages: List[Dict], model: str, api_key: str) -> AsyncGenerator[str, None]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
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
            yield f"❌ Gemini Error: {resp.json().get('error', {}).get('message', 'API error')}"
            return
        yield resp.json()["candidates"][0]["content"]["parts"][0]["text"]


async def call_groq(messages: List[Dict], model: str, api_key: str) -> AsyncGenerator[str, None]:
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    formatted = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in messages:
        formatted.append({"role": msg["role"], "content": msg["content"]})
    payload = {"model": model, "messages": formatted, "max_tokens": 2048, "temperature": 0.7}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code != 200:
            yield f"❌ Groq Error: {resp.json().get('error', {}).get('message', 'API error')}"
            return
        yield resp.json()["choices"][0]["message"]["content"]


async def call_claude(messages: List[Dict], model: str, api_key: str) -> AsyncGenerator[str, None]:
    url = "https://api.anthropic.com/v1/messages"
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
    formatted = [{"role": msg["role"], "content": msg["content"]} for msg in messages]
    payload = {"model": model, "max_tokens": 2048, "system": SYSTEM_PROMPT, "messages": formatted}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code != 200:
            yield f"❌ Claude Error: {resp.json().get('error', {}).get('message', 'API error')}"
            return
        yield resp.json()["content"][0]["text"]


async def generate_response(messages, provider, model, api_key) -> AsyncGenerator[str, None]:
    if provider == "gemini":
        async for chunk in call_gemini(messages, model, api_key): yield chunk
    elif provider == "groq":
        async for chunk in call_groq(messages, model, api_key): yield chunk
    elif provider == "claude":
        async for chunk in call_claude(messages, model, api_key): yield chunk
    else:
        yield f"❌ Unknown provider: {provider}"
