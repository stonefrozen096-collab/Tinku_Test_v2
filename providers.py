"""
Tinku Agent — providers.py
Phase 2: GNews search, source tracking, report generation
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
            {"id": "gemini-1.5-flash-latest", "name": "Gemini 1.5 Flash", "badge": "Stable • Free"},
            {"id": "gemini-1.5-pro-latest", "name": "Gemini 1.5 Pro", "badge": "Most Capable • Free"},
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
Always be respectful and never generate harmful content.
When you receive tool results (weather data, news, search results), ALWAYS use them
to give accurate, up-to-date answers. Present data cleanly with emojis.
IMPORTANT: Always use provided real-time tool data. Never say you lack real-time access
when tool data is provided.
CRITICAL: When writing reports, NEVER include memory context like [Memory about user...]
in the report title or content. Reports must be clean professional documents only."""

INAPPROPRIATE_KEYWORDS = [
    "kill", "murder", "bomb", "weapon", "hack", "porn", "nude", "suicide",
    "drug synthesis", "make meth", "child abuse", "terrorist"
]

# ═══════════════════════════════════════
# TOOL DETECTION
# ═══════════════════════════════════════

WEATHER_KEYWORDS = ["weather", "temperature", "forecast", "rain", "sunny", "humid",
    "climate", "hot", "cold", "wind", "storm", "umbrella", "celsius", "heat",
    "raining", "cloudy", "snow", "drizzle"]

SEARCH_KEYWORDS = ["latest", "news", "today", "current", "recent", "2024", "2025",
    "who is", "what happened", "trending", "update", "now", "live", "price of",
    "stock", "score", "result", "election", "breaking", "new release", "just announced"]

CURRENCY_KEYWORDS = ["convert", "exchange rate", "usd", "inr", "eur", "gbp",
    "rupee", "dollar", "euro", "pound", "currency", "forex", "how much is"]

REPORT_KEYWORDS = ["prepare a report", "generate a report", "make a report",
    "write a report", "create a report", "research report", "detailed report",
    "comprehensive report", "full report", "report on", "report about"]


def extract_city_from_message(message: str) -> Optional[str]:
    """Extract city name from message."""
    patterns = [
        r'(?:weather|temperature|forecast|climate)\s+(?:in|at|for|of)?\s*([a-zA-Z\s]+?)(?:\?|$|today|tomorrow|now)',
        r'(?:in|at|for)\s+([A-Z][a-zA-Z\s]+?)(?:\?|$|weather|today|tomorrow)',
        r'([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?)\s+(?:weather|temperature|forecast)',
    ]
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            city = match.group(1).strip().title()
            if len(city) > 2 and city.lower() not in ['the', 'what', 'how', 'why', 'when']:
                return city
    return None


def detect_tools_needed(message: str) -> dict:
    """Detect which tools are needed."""
    lower = message.lower()
    tools = {
        "weather": False, "search": False,
        "currency": False, "report": False,
        "city": None
    }
    if any(kw in lower for kw in WEATHER_KEYWORDS):
        tools["weather"] = True
        tools["city"] = extract_city_from_message(message) or "Mumbai"
    if any(kw in lower for kw in SEARCH_KEYWORDS):
        tools["search"] = True
    if any(kw in lower for kw in CURRENCY_KEYWORDS):
        tools["currency"] = True
    if any(kw in lower for kw in REPORT_KEYWORDS):
        tools["report"] = True
        tools["search"] = True  # Reports always need search
    return tools


# ═══════════════════════════════════════
# TOOL: LIVE WEATHER
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


async def geocode_city(city: str) -> Optional[Tuple]:
    """Get coordinates for any city."""
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


async def get_weather(city: str) -> dict:
    """Fetch live weather. Returns data + source."""
    try:
        geo = await geocode_city(city)
        if not geo:
            return {"data": f"⚠️ Could not find weather for '{city}'.", "sources": []}
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
        result = f"""🌍 **Live Weather — {full_name}**

{condition}
🌡️ **{c['temperature_2m']}°C** (Feels like {c['apparent_temperature']}°C)
💧 Humidity: {c['relative_humidity_2m']}% | 🌧 Rain: {c['precipitation_probability']}%
💨 Wind: {c['wind_speed_10m']} km/h | ☀️ UV: {c['uv_index']}

**3-Day Forecast:**
📅 Today: {d['temperature_2m_min'][0]}°C – {d['temperature_2m_max'][0]}°C {condition} Rain: {d['precipitation_probability_max'][0]}%
📅 Tomorrow: {d['temperature_2m_min'][1]}°C – {d['temperature_2m_max'][1]}°C {day2} Rain: {d['precipitation_probability_max'][1]}%
📅 Day 3: {d['temperature_2m_min'][2]}°C – {d['temperature_2m_max'][2]}°C {day3} Rain: {d['precipitation_probability_max'][2]}%"""
        return {
            "data": result,
            "sources": [{"title": f"Live Weather — {full_name}", "url": "https://open-meteo.com", "source": "Open-Meteo"}]
        }
    except Exception as e:
        return {"data": f"⚠️ Weather fetch failed: {str(e)}", "sources": []}


# ═══════════════════════════════════════
# TOOL: GNEWS SEARCH (Real News!)
# ═══════════════════════════════════════

def extract_search_query(message: str) -> str:
    """Extract a clean short query from user message for better search results."""
    # Remove conversational filler words
    noise = [
        "can you", "could you", "please", "tell me", "show me", "give me",
        "what is", "what are", "what's", "i want to know", "i need",
        "search for", "look up", "find", "get me", "fetch",
        "latest", "recent", "current", "today", "now", "live",
        "news on", "news about", "updates on", "updates about",
        "information on", "information about", "info on", "info about",
        "details on", "details about", "about", "on the topic of",
    ]
    q = message.lower().strip()
    for n in noise:
        q = q.replace(n, " ")
    # Clean up extra spaces and punctuation
    q = re.sub(r'[?!.,]+', '', q)
    q = re.sub(r'\s+', ' ', q).strip()
    # Keep it short — max 5 words
    words = q.split()
    if len(words) > 5:
        q = ' '.join(words[:5])
    return q or message[:50]


async def web_search(query: str) -> dict:
    """Search using GNews API (real news) with smart query + Wikipedia fallback."""
    sources = []
    results = []

    # Extract clean short query for better results
    clean_query = extract_search_query(query)

    # Try GNews first (real news articles!)
    gnews_key = settings.GNEWS_API_KEY
    if gnews_key:
        try:
            url = "https://gnews.io/api/v4/search"
            params = {
                "q": clean_query, "lang": "en", "max": 5,
                "apikey": gnews_key, "sortby": "publishedAt"
            }
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, params=params)
                data = resp.json()

            articles = data.get("articles", [])
            if articles:
                results.append("📰 **Latest News:**\n")
                for i, a in enumerate(articles[:4]):
                    title = a.get("title", "")
                    desc = a.get("description", "")[:150]
                    source_name = a.get("source", {}).get("name", "News")
                    article_url = a.get("url", "")
                    pub_date = a.get("publishedAt", "")[:10]
                    results.append(f"**{i+1}. {title}**\n{desc}...\n📅 {pub_date} | 📰 {source_name}")
                    sources.append({"title": title, "url": article_url, "source": source_name})
        except Exception as e:
            pass

    # Try DuckDuckGo as second source
    if not results:
        try:
            url = "https://api.duckduckgo.com/"
            params = {"q": clean_query, "format": "json", "no_html": "1", "skip_disambig": "1"}
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.get(url, params=params)
                data = resp.json()
            if data.get("Abstract"):
                results.append(f"📖 **{data.get('Heading', 'Result')}:**\n{data['Abstract'][:400]}")
                if data.get("AbstractURL"):
                    sources.append({"title": data.get("Heading", query), "url": data["AbstractURL"], "source": "DuckDuckGo"})
            if data.get("Answer"):
                results.append(f"✅ **Answer:** {data['Answer']}")
        except:
            pass

    # Wikipedia fallback
    try:
        wiki_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{clean_query.replace(' ', '_')}"
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(wiki_url)
            if resp.status_code == 200:
                wiki = resp.json()
                if wiki.get("extract") and len(wiki["extract"]) > 50:
                    results.append(f"\n📚 **Wikipedia — {wiki.get('title', query)}:**\n{wiki['extract'][:400]}")
                    wiki_page = wiki.get("content_urls", {}).get("desktop", {}).get("page", "")
                    if wiki_page:
                        sources.append({"title": f"Wikipedia — {wiki.get('title', query)}", "url": wiki_page, "source": "Wikipedia"})
    except:
        pass

    search_text = "\n\n".join(results) if results else f"No results found for '{clean_query}'."
    return {
        "data": "🔍 **Search Results:**\n\n" + search_text if results else search_text,
        "sources": sources
    }


# ═══════════════════════════════════════
# TOOL: CURRENCY
# ═══════════════════════════════════════

async def get_exchange_rate() -> dict:
    """Get live exchange rates."""
    try:
        url = "https://open.er-api.com/v6/latest/USD"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            data = resp.json()
        rates = data.get("rates", {})
        result = f"""💱 **Live Exchange Rates (Base: USD)**

🇮🇳 1 USD = ₹{rates.get('INR', 83.5):.2f} INR
🇪🇺 1 USD = €{rates.get('EUR', 0.92):.4f} EUR
🇬🇧 1 USD = £{rates.get('GBP', 0.79):.4f} GBP
🇯🇵 1 USD = ¥{rates.get('JPY', 149.5):.2f} JPY
🇦🇪 1 USD = {rates.get('AED', 3.67):.2f} AED
🇸🇬 1 USD = S${rates.get('SGD', 1.34):.4f} SGD

*Updated: {data.get('time_last_update_utc', 'Recently')}*"""
        return {
            "data": result,
            "sources": [{"title": "Live Exchange Rates", "url": "https://open.er-api.com", "source": "ExchangeRate-API"}]
        }
    except:
        return {"data": "💱 Exchange rates temporarily unavailable.", "sources": []}


# ═══════════════════════════════════════
# TOOL: REPORT GENERATION PROMPT
# ═══════════════════════════════════════

def build_report_prompt(topic: str, search_data: str) -> str:
    """Build a structured report prompt — clean, no memory context."""
    return f"""Generate a comprehensive, professional report about: {topic}

Research Data Available:
{search_data}

IMPORTANT RULES:
- Do NOT include any memory about the user in the report
- Do NOT include phrases like "[Memory about user...]" anywhere
- The report title should be ONLY about the topic: "{topic.title()}"
- Write as a professional research document

Use EXACTLY this structure:

# {topic.title()} — Comprehensive Report

## 📋 Executive Summary
[2-3 sentence overview of the topic]

## 🔍 Key Findings
[7 bullet points of most important facts with emojis]

## 📊 Detailed Analysis
[3-4 paragraphs of in-depth analysis]

## 🌍 Current Trends
[Latest developments and trends]

## 💡 Insights & Recommendations
[5 actionable insights with emojis]

## 📝 Conclusion
[2-3 sentence wrap up]

---
*Report generated by Tinku AI Agent*
*Sources: Based on latest available data*

Make it professional, thorough and informative."""


# ═══════════════════════════════════════
# CONTENT MODERATION
# ═══════════════════════════════════════

def check_content(text: str) -> tuple:
    lower = text.lower()
    for kw in INAPPROPRIATE_KEYWORDS:
        if kw in lower:
            return True, f"Contains potentially inappropriate content: '{kw}'"
    return False, ""


# ═══════════════════════════════════════
# AI PROVIDERS
# ═══════════════════════════════════════

async def call_gemini(messages: List[Dict], model: str, api_key: str, memory: str = "") -> AsyncGenerator[str, None]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})
    payload = {
        "contents": contents,
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT + memory}]},
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 4096},
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code != 200:
            yield f"❌ Gemini Error: {resp.json().get('error', {}).get('message', 'API error')}"
            return
        yield resp.json()["candidates"][0]["content"]["parts"][0]["text"]


async def call_groq(messages: List[Dict], model: str, api_key: str, memory: str = "") -> AsyncGenerator[str, None]:
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    formatted = [{"role": "system", "content": SYSTEM_PROMPT + memory}]
    for msg in messages:
        formatted.append({"role": msg["role"], "content": msg["content"]})
    payload = {"model": model, "messages": formatted, "max_tokens": 4096, "temperature": 0.7}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code != 200:
            yield f"❌ Groq Error: {resp.json().get('error', {}).get('message', 'API error')}"
            return
        yield resp.json()["choices"][0]["message"]["content"]


async def call_claude(messages: List[Dict], model: str, api_key: str, memory: str = "") -> AsyncGenerator[str, None]:
    url = "https://api.anthropic.com/v1/messages"
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
    formatted = [{"role": msg["role"], "content": msg["content"]} for msg in messages]
    payload = {"model": model, "max_tokens": 4096, "system": SYSTEM_PROMPT + memory, "messages": formatted}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code != 200:
            yield f"❌ Claude Error: {resp.json().get('error', {}).get('message', 'API error')}"
            return
        yield resp.json()["content"][0]["text"]


async def generate_response(messages, provider, model, api_key, memory: str = "") -> AsyncGenerator[str, None]:
    if provider == "gemini":
        async for chunk in call_gemini(messages, model, api_key, memory): yield chunk
    elif provider == "groq":
        async for chunk in call_groq(messages, model, api_key, memory): yield chunk
    elif provider == "claude":
        async for chunk in call_claude(messages, model, api_key, memory): yield chunk
    else:
        yield f"❌ Unknown provider: {provider}"
