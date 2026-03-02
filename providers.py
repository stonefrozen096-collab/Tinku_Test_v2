"""
AI Provider Abstraction Layer — Tinku Agent v3
Fixed: More cities, better search, geocoding API
"""
import httpx
import json
import re
from typing import AsyncGenerator, List, Dict, Optional, Tuple
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
accurate, helpful answers. Present data in a clean, readable format with emojis.
IMPORTANT: Always use the provided real-time tool data. Never say you don't have
real-time access when tool data is provided to you."""

INAPPROPRIATE_KEYWORDS = [
    "kill", "murder", "bomb", "weapon", "hack", "porn", "nude", "suicide",
    "drug synthesis", "make meth", "child abuse", "terrorist"
]

# ═══════════════════════════════════════
# TOOL DETECTION
# ═══════════════════════════════════════

WEATHER_KEYWORDS = ["weather", "temperature", "forecast", "rain", "sunny", "humid",
    "climate", "hot", "cold", "wind", "storm", "umbrella", "celsius", "heat",
    "raining", "cloudy", "snow", "drizzle", "climate today"]

SEARCH_KEYWORDS = ["latest", "news", "today", "current", "recent", "2024", "2025",
    "who is", "what happened", "trending", "update", "now", "live", "price of",
    "stock", "score", "result", "election", "breaking", "new release", "just announced"]

CURRENCY_KEYWORDS = ["convert", "exchange rate", "usd", "inr", "eur", "gbp",
    "rupee", "dollar", "euro", "pound", "currency", "forex", "how much is"]


def extract_city_from_message(message: str) -> Optional[str]:
    """Extract any city name from the message using common patterns."""
    lower = message.lower()

    # Pattern: "in <city>", "at <city>", "for <city>", "weather <city>"
    patterns = [
        r'(?:weather|temperature|forecast|climate)\s+(?:in|at|for|of)?\s*([a-zA-Z\s]+?)(?:\?|$|today|tomorrow|now)',
        r'(?:in|at|for)\s+([A-Z][a-zA-Z\s]+?)(?:\?|$|weather|today|tomorrow)',
        r'([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?)\s+(?:weather|temperature|forecast)',
    ]

    import re as re_mod
    for pattern in patterns:
        match = re_mod.search(pattern, message, re_mod.IGNORECASE)
        if match:
            city = match.group(1).strip().title()
            if len(city) > 2 and city.lower() not in ['the', 'what', 'how', 'why', 'when']:
                return city
    return None


def detect_tools_needed(message: str) -> dict:
    """Detect which tools are needed for this message."""
    lower = message.lower()
    tools = {"weather": False, "search": False, "currency": False, "city": None}

    if any(kw in lower for kw in WEATHER_KEYWORDS):
        tools["weather"] = True
        # Try smart city extraction first
        city = extract_city_from_message(message)
        tools["city"] = city or "Mumbai"

    if any(kw in lower for kw in SEARCH_KEYWORDS):
        tools["search"] = True

    if any(kw in lower for kw in CURRENCY_KEYWORDS):
        tools["currency"] = True

    return tools


# ═══════════════════════════════════════
# TOOL: LIVE WEATHER (Open-Meteo + Geocoding)
# ═══════════════════════════════════════

WMO_CODES = {
    0: "☀️ Clear sky", 1: "🌤 Mainly clear", 2: "⛅ Partly cloudy",
    3: "☁️ Overcast", 45: "🌫 Foggy", 48: "🌫 Icy fog",
    51: "🌦 Light drizzle", 53: "🌦 Drizzle", 55: "🌧 Heavy drizzle",
    61: "🌧 Light rain", 63: "🌧 Rain", 65: "🌧 Heavy rain",
    71: "🌨 Light snow", 73: "❄️ Snow", 75: "❄️ Heavy snow",
    80: "🌦 Light showers", 81: "🌧 Showers", 82: "⛈ Heavy showers",
    95: "⛈ Thunderstorm", 96: "⛈ Thunderstorm with hail",
}


async def geocode_city(city: str) -> Optional[tuple]:
    """Get coordinates for ANY city using Open-Meteo Geocoding API (free!)."""
    try:
        url = "https://geocoding-api.open-meteo.com/v1/search"
        params = {"name": city, "count": 1, "language": "en", "format": "json"}
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
            data = resp.json()

        results = data.get("results", [])
        if results:
            r = results[0]
            name = f"{r.get('name', city)}, {r.get('country', '')}"
            return r["latitude"], r["longitude"], name
        return None
    except:
        return None


async def get_weather(city: str) -> str:
    """Fetch live weather for ANY city using geocoding + Open-Meteo."""
    try:
        # Geocode the city to get exact coordinates
        geo = await geocode_city(city)
        if not geo:
            return f"⚠️ Could not find weather for '{city}'. Please check the city name!"

        lat, lon, full_name = geo

        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
            f"precipitation_probability,weather_code,wind_speed_10m,uv_index"
            f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"
            f"&timezone=auto&forecast_days=3"
        )

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            data = resp.json()

        c = data["current"]
        d = data["daily"]
        condition = WMO_CODES.get(c["weather_code"], "🌡 Unknown")
        day2 = WMO_CODES.get(d["weather_code"][1], "")
        day3 = WMO_CODES.get(d["weather_code"][2], "")

        return f"""🌍 **Live Weather — {full_name}**

{condition}
🌡️ **{c['temperature_2m']}°C** (Feels like {c['apparent_temperature']}°C)
💧 Humidity: {c['relative_humidity_2m']}%
🌧 Rain chance: {c['precipitation_probability']}%
💨 Wind: {c['wind_speed_10m']} km/h | ☀️ UV Index: {c['uv_index']}

**3-Day Forecast:**
📅 Today: {d['temperature_2m_min'][0]}°C – {d['temperature_2m_max'][0]}°C {condition} Rain: {d['precipitation_probability_max'][0]}%
📅 Tomorrow: {d['temperature_2m_min'][1]}°C – {d['temperature_2m_max'][1]}°C {day2} Rain: {d['precipitation_probability_max'][1]}%
📅 Day 3: {d['temperature_2m_min'][2]}°C – {d['temperature_2m_max'][2]}°C {day3} Rain: {d['precipitation_probability_max'][2]}%"""

    except Exception as e:
        return f"⚠️ Weather fetch failed for '{city}': {str(e)}"


# ═══════════════════════════════════════
# TOOL: WEB SEARCH (Wikipedia API — more reliable!)
# ═══════════════════════════════════════

async def web_search(query: str) -> str:
    """Search using Wikipedia API + DuckDuckGo for current info."""
    results = []

    # Try DuckDuckGo first
    try:
        url = "https://api.duckduckgo.com/"
        params = {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(url, params=params)
            data = resp.json()

        if data.get("Abstract"):
            results.append(f"📖 **{data.get('Heading', 'Result')}:**\n{data['Abstract'][:500]}")
            if data.get("AbstractURL"):
                results.append(f"🔗 {data['AbstractURL']}")

        if data.get("Answer"):
            results.append(f"✅ **Answer:** {data['Answer']}")

        topics = [t for t in data.get("RelatedTopics", [])[:3] if isinstance(t, dict) and t.get("Text")]
        if topics:
            results.append("\n📰 **Related:**")
            for t in topics:
                results.append(f"• {t['Text'][:120]}")
    except:
        pass

    # Try Wikipedia for factual queries
    try:
        wiki_url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + query.replace(" ", "_")
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(wiki_url)
            if resp.status_code == 200:
                wiki = resp.json()
                if wiki.get("extract") and len(wiki["extract"]) > 50:
                    results.append(f"\n📚 **Wikipedia — {wiki.get('title', query)}:**\n{wiki['extract'][:400]}")
                    results.append(f"🔗 {wiki.get('content_urls', {}).get('desktop', {}).get('page', '')}")
    except:
        pass

    if results:
        return "🔍 **Search Results:**\n\n" + "\n".join(results)

    return f"🔍 Searched for: '{query}'\n\n⚠️ Limited results found. Here's what I know from training:"


# ═══════════════════════════════════════
# TOOL: CURRENCY
# ═══════════════════════════════════════

async def get_exchange_rate() -> str:
    """Get live exchange rates."""
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
