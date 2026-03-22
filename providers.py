"""
Tinku Agent — providers.py
Phase 2: GNews search, source tracking, report generation
"""
import httpx
import os
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
            {"id": "claude-sonnet-4-5-20251001", "name": "Claude Sonnet 4.5", "badge": "Recommended"},
            {"id": "claude-opus-4-5-20251001", "name": "Claude Opus 4.5", "badge": "Most Powerful"},
            {"id": "claude-haiku-4-5-20251001", "name": "Claude Haiku 4.5", "badge": "Fastest"},
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


CODE_KEYWORDS = ["run this code", "execute this", "run this python", "execute python",
    "run the code", "execute the code", "run code", "test this code", "execute this code"]
SONG_KEYWORDS = ["find song","search song","play song","find music","song by","music by","find the song","get song","find a song","search for song","find me a song"]
STOCK_KEYWORDS = ["stock price","share price","crypto price","bitcoin price","ethereum price","nifty","sensex","nasdaq","btc price","eth price","market price","trading at","current price of"]
RESEARCH_KEYWORDS = ["research on","deep research","detailed research","in depth research","comprehensive research","research about","find everything about","tell me everything about"]

def extract_url_from_message(message: str) -> Optional[str]:
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    match = re.search(url_pattern, message)
    if match:
        return match.group(0)
    www_pattern = r'www\.[^\s<>"{}|\\^`\[\]]+'
    match = re.search(www_pattern, message)
    if match:
        return "https://" + match.group(0)
    return None

def extract_code_from_message(message: str) -> Optional[str]:
    for pattern in [r'```python\s*([\s\S]+?)```', r'```\s*([\s\S]+?)```', r'`([^`]+)`']:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None

def detect_tools_needed(message: str, has_file: bool = False) -> dict:
    """Detect which tools are needed — Phase 6."""
    lower = message.lower()
    tools = {
        "weather": False, "search": False, "currency": False, "report": False,
        "url": False, "file": False, "code": False,
        "song": False, "stock": False, "research": False, "vision": False,
        "sentiment": False, "summarize": False, "chart": False, "translate": False,
        # Phase 6
        "pdf_export": False, "docx_export": False,
        "note_save": False, "note_recall": False,
        "todo_add": False, "todo_show": False, "todo_done": False,
        "meme": False, "resume": False,
        "city": None, "url_value": None
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
        tools["search"] = True
    url = extract_url_from_message(message)
    if url:
        tools["url"] = True
        tools["url_value"] = url
    if has_file:
        tools["file"] = True
    if any(kw in lower for kw in CODE_KEYWORDS) or "```" in message:
        tools["code"] = True
    if any(kw in lower for kw in SONG_KEYWORDS): tools["song"] = True
    if any(kw in lower for kw in STOCK_KEYWORDS): tools["stock"] = True
    if any(kw in lower for kw in RESEARCH_KEYWORDS):
        tools["research"] = True
        tools["search"] = True
    if any(kw in lower for kw in SENTIMENT_KEYWORDS): tools["sentiment"] = True
    if any(kw in lower for kw in SUMMARIZE_KEYWORDS): tools["summarize"] = True
    if any(kw in lower for kw in CHART_KEYWORDS): tools["chart"] = True
    if any(kw in lower for kw in TRANSLATE_KEYWORDS): tools["translate"] = True
    # Phase 6 tool detection
    if any(kw in lower for kw in PDF_KEYWORDS): tools["pdf_export"] = True
    if any(kw in lower for kw in DOCX_KEYWORDS): tools["docx_export"] = True
    if any(kw in lower for kw in NOTE_KEYWORDS): tools["note_save"] = True
    if any(kw in lower for kw in RECALL_KEYWORDS): tools["note_recall"] = True
    if any(kw in lower for kw in TODO_KEYWORDS): tools["todo_add"] = True
    if any(kw in lower for kw in SHOW_TODO_KEYWORDS): tools["todo_show"] = True
    if any(kw in lower for kw in DONE_TODO_KEYWORDS): tools["todo_done"] = True
    if any(kw in lower for kw in RESUME_KEYWORDS): tools["resume"] = True
    # Fix: "convert to pdf" should NOT trigger currency
    if tools["pdf_export"] or tools["docx_export"]:
        tools["currency"] = False
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


# ═══════════════════════════════════════
# PHASE 15: SEARCH DB + SMART EXPIRY
# ═══════════════════════════════════════

import hashlib
from datetime import datetime, timedelta

# Smart expiry rules (minutes)
CACHE_EXPIRY = {
    "news":     60,       # 1 hour
    "weather":  30,       # 30 minutes
    "stock":    5,        # 5 minutes
    "wiki":     43200,    # 30 days
    "general":  1440,     # 24 hours
}

def get_cache_type(query: str) -> str:
    """Detect query type for smart expiry."""
    q = query.lower()
    if any(w in q for w in ["news", "latest", "today", "breaking", "current"]):
        return "news"
    if any(w in q for w in ["weather", "temperature", "forecast", "rain"]):
        return "weather"
    if any(w in q for w in ["stock", "price", "crypto", "bitcoin", "market"]):
        return "stock"
    if any(w in q for w in ["wikipedia", "history", "what is", "who is", "define"]):
        return "wiki"
    return "general"

def get_query_hash(query: str) -> str:
    """Generate consistent hash for query."""
    return hashlib.md5(query.lower().strip().encode()).hexdigest()

async def get_cached_search(db, query: str) -> dict:
    """Check MongoDB for cached search result."""
    if db is None:
        return None
    try:
        query_hash = get_query_hash(query)
        cache_type = get_cache_type(query)
        expiry_mins = CACHE_EXPIRY[cache_type]
        expiry_time = datetime.utcnow() - timedelta(minutes=expiry_mins)

        cached = await db.search_cache.find_one({
            "query_hash": query_hash,
            "cached_at": {"$gt": expiry_time}
        })

        if cached:
            return {
                "data": cached["data"],
                "sources": cached.get("sources", []),
                "from_cache": True
            }
    except Exception:
        pass
    return None

async def save_search_cache(db, query: str, data: str, sources: list):
    """Save search result to MongoDB cache."""
    if db is None:
        return
    try:
        query_hash = get_query_hash(query)
        await db.search_cache.update_one(
            {"query_hash": query_hash},
            {"$set": {
                "query_hash":  query_hash,
                "query":       query[:200],
                "data":        data,
                "sources":     sources,
                "cache_type":  get_cache_type(query),
                "cached_at":   datetime.utcnow()
            }},
            upsert=True
        )
    except Exception:
        pass

async def web_search(query: str, db=None) -> dict:
    """
    Phase 15+16: Search DB cache first, then Tavily/GNews/Wikipedia.
    Priority: MongoDB Cache → Tavily → GNews → DuckDuckGo → Wikipedia
    """
    # ── Check cache first ──
    if db is not None:
        cached = await get_cached_search(db, query)
        if cached:
            return cached
    sources = []
    results = []
    clean_query = extract_search_query(query)

    # ── TAVILY SEARCH (Primary — Full Web, Built for AI) ──
    tavily_key = os.getenv("TAVILY_API_KEY", "")
    if tavily_key:
        try:
            url = "https://api.tavily.com/search"
            payload = {
                "api_key":              tavily_key,
                "query":                clean_query,
                "search_depth":         "basic",
                "include_answer":       True,
                "include_raw_content":  False,
                "max_results":          5,
                "include_domains":      [],
                "exclude_domains":      []
            }
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload)
                data = resp.json()

            # Show AI answer if available
            answer = data.get("answer", "")
            if answer:
                results.append(f"✅ **Answer:** {answer[:300]}")

            # Show web results
            web_results = data.get("results", [])
            if web_results:
                results.append("\n🔍 **Search Results:**\n")
                for i, r in enumerate(web_results[:5]):
                    title   = r.get("title", "")
                    content = r.get("content", "")[:200]
                    result_url = r.get("url", "")
                    site    = result_url.split("/")[2] if result_url else ""
                    score   = r.get("score", 0)
                    results.append(f"**{i+1}. {title}**\n{content}\n🔗 {site}")
                    sources.append({"title": title, "url": result_url, "source": site})

        except Exception as e:
            pass

    # ── GNEWS (Fallback for news queries) ──
    if not results:
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
            except:
                pass

    # ── DUCKDUCKGO (Fallback) ──
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

    # ── WIKIPEDIA (Always try as extra context) ──
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
    result = {
        "data": "🔍 **Search Results:**\n\n" + search_text if results else search_text,
        "sources": sources
    }

    # ── Save to cache ──
    if results and db is not None:
        await save_search_cache(db, query, result["data"], sources)

    return result


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
    import re
    lower = text.lower()
    for kw in INAPPROPRIATE_KEYWORDS:
        # Use word boundary to avoid false positives like skilled/kill
        pattern = r'\b' + re.escape(kw) + r'\b'
        if re.search(pattern, lower):
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


# PHASE 3 TOOLS

async def fetch_url_content(url: str) -> dict:
    """Fetch and extract text content from any URL."""
    try:
        # Clean URL
        if not url.startswith("http"):
            url = "https://" + url

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)

        content_type = resp.headers.get("content-type", "")

        if "text/html" in content_type:
            # Extract text from HTML
            html = resp.text
            # Remove scripts, styles, nav etc
            import re
            html = re.sub(r'<script[^>]*>[\s\S]*?</script>', '', html, flags=re.IGNORECASE)
            html = re.sub(r'<style[^>]*>[\s\S]*?</style>', '', html, flags=re.IGNORECASE)
            html = re.sub(r'<nav[^>]*>[\s\S]*?</nav>', '', html, flags=re.IGNORECASE)
            html = re.sub(r'<footer[^>]*>[\s\S]*?</footer>', '', html, flags=re.IGNORECASE)
            html = re.sub(r'<header[^>]*>[\s\S]*?</header>', '', html, flags=re.IGNORECASE)
            # Extract title
            title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE)
            title = title_match.group(1).strip() if title_match else url
            # Remove all HTML tags
            text = re.sub(r'<[^>]+>', ' ', html)
            # Clean whitespace
            text = re.sub(r'\s+', ' ', text).strip()
            # Limit to 3000 chars for AI
            text = text[:3000] + ("..." if len(text) > 3000 else "")

            return {
                "data": f"📄 **Content from:** {title}\n**URL:** {url}\n\n{text}",
                "title": title,
                "url": url,
                "sources": [{"title": title, "url": url, "source": "URL Content"}]
            }

        elif "application/pdf" in content_type:
            return {
                "data": f"📄 PDF detected at {url}. Please download and upload the file directly for analysis.",
                "sources": [{"title": "PDF URL", "url": url, "source": "URL"}]
            }

        else:
            text = resp.text[:2000]
            return {
                "data": f"📄 **Content from {url}:**\n\n{text}",
                "sources": [{"title": url, "url": url, "source": "URL Content"}]
            }

    except Exception as e:
        return {
            "data": f"⚠️ Could not fetch URL: {str(e)}\nMake sure the URL is correct and accessible.",
            "sources": []
        }


# ═══════════════════════════════════════
# TOOL: FILE ANALYSIS
# ═══════════════════════════════════════

async def analyze_file(file_content: str, file_name: str) -> dict:
    """Analyze uploaded file content."""
    try:
        result = ""
        file_ext = file_name.lower().split('.')[-1] if '.' in file_name else ''

        if file_ext == 'csv':
            # Parse CSV
            lines = file_content.strip().split('\n')
            headers = lines[0] if lines else ""
            row_count = len(lines) - 1
            preview = '\n'.join(lines[:6])  # First 5 rows
            result = f"""📊 **CSV File Analysis: {file_name}**

📋 **Columns:** {headers}
📈 **Total Rows:** {row_count}

**Preview (first 5 rows):**
```
{preview}
```

**Full Data for Analysis:**
{file_content[:3000]}"""

        elif file_ext in ['txt', 'md', 'py', 'js', 'html', 'css', 'json']:
            word_count = len(file_content.split())
            line_count = len(file_content.split('\n'))
            result = f"""📄 **File: {file_name}**
📊 Words: {word_count} | Lines: {line_count}

**Content:**
{file_content[:3000]}{'...' if len(file_content) > 3000 else ''}"""

        elif file_ext == 'json':
            try:
                parsed = json.loads(file_content)
                result = f"""📋 **JSON File: {file_name}**

**Structure:**
{json.dumps(parsed, indent=2)[:2000]}"""
            except:
                result = f"📋 **File: {file_name}**\n\n{file_content[:2000]}"

        else:
            result = f"📄 **File: {file_name}**\n\n{file_content[:2000]}"

        return {
            "data": result,
            "sources": [{"title": f"File: {file_name}", "url": "#", "source": "Uploaded File"}]
        }

    except Exception as e:
        return {
            "data": f"⚠️ Could not analyze file: {str(e)}",
            "sources": []
        }


# ═══════════════════════════════════════
# TOOL: CODE EXECUTION (Safe Sandbox)
# ═══════════════════════════════════════

async def execute_code(code: str) -> dict:
    """Execute Python code safely using Piston API (free)."""
    try:
        url = "https://emkc.org/api/v2/piston/execute"
        payload = {
            "language": "python",
            "version": "3.10",
            "files": [{"content": code}],
            "stdin": "",
            "args": [],
            "compile_timeout": 10000,
            "run_timeout": 5000
        }
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()

        run = data.get("run", {})
        output = run.get("stdout", "").strip()
        stderr = run.get("stderr", "").strip()
        exit_code = run.get("code", 0)

        if stderr and not output:
            result = f"❌ **Error:**\n```\n{stderr}\n```"
        elif stderr:
            result = f"✅ **Output:**\n```\n{output}\n```\n\n⚠️ **Warnings:**\n```\n{stderr}\n```"
        elif output:
            result = f"✅ **Output:**\n```\n{output}\n```"
        else:
            result = "✅ Code executed successfully (no output)"

        return {
            "data": f"💻 **Code Execution Result:**\n\n{result}",
            "output": output,
            "error": stderr,
            "exit_code": exit_code,
            "sources": [{"title": "Code Execution", "url": "https://emkc.org", "source": "Piston API"}]
        }

    except Exception as e:
        return {
            "data": f"⚠️ Code execution failed: {str(e)}",
            "output": "", "error": str(e), "exit_code": 1,
            "sources": []
        }


# ═══════════════════════════════════════
# HELPER: Extract URL from message
# ═══════════════════════════════════════

def extract_song_query(message: str) -> str:
    import re as _re
    for pat in [r'find (?:song|music)[:\s]+(.+)', r'search (?:for )?(?:song|music)[:\s]+(.+)',
                r'play[:\s]+(.+)', r'(?:song|music) by[:\s]+(.+)', r'find (?:me )?(?:the )?song[:\s]+(.+)']:
        m = _re.search(pat, message, _re.IGNORECASE)
        if m:
            return m.group(1).strip().rstrip('?.')
    w = message.lower()
    for kw in ['find song','search song','play song','find music','search music','find me a song','find the song','get song']:
        w = w.replace(kw, '').strip()
    return w.strip() or message.strip()


async def search_song(query: str) -> dict:
    try:
        encoded = query.strip().replace(' ', '+')
        url = "https://itunes.apple.com/search?term=" + encoded + "&media=music&limit=3"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            data = resp.json()
        results = data.get("results", [])
        if not results:
            return {"data": "No songs found for: " + query, "songs": [], "sources": []}
        songs = []
        for r in results[:3]:
            name = r.get("trackName", "Unknown")
            artist = r.get("artistName", "Unknown")
            album = r.get("collectionName", "Unknown")
            ms = r.get("trackTimeMillis", 0)
            duration = str(ms // 60000) + ":" + str((ms % 60000) // 1000).zfill(2) if ms else "0:00"
            preview = r.get("previewUrl", "")
            artwork = r.get("artworkUrl100", "").replace("100x100", "300x300")
            apple_url = r.get("trackViewUrl", "")
            # YouTube: song name first + first artist only for better results
            first_artist = artist.split(",")[0].strip()
            yt = "https://www.youtube.com/results?search_query=" + (name + " " + first_artist).replace(" ", "+")
            sp = "https://open.spotify.com/search/" + (name + " " + first_artist).replace(" ", "%20")
            songs.append({"name": name, "artist": artist, "album": album, "duration": duration,
                          "preview": preview, "artwork": artwork, "apple_url": apple_url,
                          "youtube": yt, "spotify": sp})
        text = "🎵 **Song Results for '" + query + "':**\n\n"
        for i, s in enumerate(songs, 1):
            text += "**" + str(i) + ". " + s['name'] + "** — " + s['artist'] + "\n"
            text += "   💿 " + s['album'] + " • ⏱ " + s['duration'] + "\n\n"
        return {
            "data": text, "songs": songs,
            "sources": [{"title": s['name'] + " — " + s['artist'],
                         "url": s['apple_url'] or s['youtube'], "source": "iTunes"} for s in songs]
        }
    except Exception as e:
        return {"data": "Song search failed: " + str(e), "songs": [], "sources": []}


# ═══════════════════════════════════════
# PHASE 4: STOCK / CRYPTO PRICES
# ═══════════════════════════════════════

CRYPTO_MAP = {
    "bitcoin": "bitcoin", "btc": "bitcoin", "ethereum": "ethereum", "eth": "ethereum",
    "bnb": "binancecoin", "dogecoin": "dogecoin", "doge": "dogecoin",
    "solana": "solana", "sol": "solana", "xrp": "ripple", "ripple": "ripple",
    "ada": "cardano", "cardano": "cardano", "matic": "matic-network", "polygon": "matic-network",
    "shib": "shiba-inu", "shiba": "shiba-inu",
}


def extract_stock_query(message: str) -> str:
    for pat in [r'(?:price of|stock of|stock price of|share price of)\s+([a-zA-Z\s]+?)(?:\?|$)',
                r'([a-zA-Z]+)\s+(?:stock|share|crypto)',
                r'(?:what is|how much is)\s+([a-zA-Z\s]+?)(?:\?|$)']:
        m = re.search(pat, message, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return message.strip()


async def get_stock_price(query: str) -> dict:
    lower = query.lower().strip()
    try:
        for k, v in CRYPTO_MAP.items():
            if k in lower:
                # Use Binance API - reliable, no auth needed
                symbol_map = {
                    "bitcoin": "BTCUSDT", "btc": "BTCUSDT",
                    "ethereum": "ETHUSDT", "eth": "ETHUSDT",
                    "binancecoin": "BNBUSDT", "dogecoin": "DOGEUSDT",
                    "solana": "SOLUSDT", "ripple": "XRPUSDT",
                    "cardano": "ADAUSDT", "matic-network": "MATICUSDT",
                    "shiba-inu": "SHIBUSDT",
                }
                sym = symbol_map.get(v, v.upper() + "USDT")
                url = "https://api.binance.com/api/v3/ticker/24hr?symbol=" + sym
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(url)
                    data = resp.json()
                if data.get("lastPrice"):
                    usd = float(data["lastPrice"])
                    chg = float(data.get("priceChangePercent", 0))
                    high = float(data.get("highPrice", 0))
                    low = float(data.get("lowPrice", 0))
                    arrow = "📈" if chg >= 0 else "📉"
                    result = ("💰 **" + query.upper() + " Price**\n\n"
                              "💵 USD: $" + "{:,.4f}".format(usd) + "\n"
                              + arrow + " 24h Change: " + "{:+.2f}".format(chg) + "%\n"
                              "📈 24h High: $" + "{:,.4f}".format(high) + "\n"
                              "📉 24h Low: $" + "{:,.4f}".format(low) + "\n\n"
                              "*Live via Binance*")
                    return {"data": result, "sources": [{"title": query.upper() + " Price", "url": "https://binance.com", "source": "Binance"}]}
        sym = query.upper().replace(" ", "")
        url = "https://query1.finance.yahoo.com/v8/finance/chart/" + sym + "?interval=1d&range=1d"
        async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "Mozilla/5.0"}) as client:
            resp = await client.get(url)
            data = resp.json()
        meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
        price = meta.get("regularMarketPrice", 0)
        prev = meta.get("chartPreviousClose", 0)
        chg = ((price - prev) / prev * 100) if prev else 0
        cur = meta.get("currency", "USD")
        name = meta.get("longName", sym)
        arrow = "📈" if chg >= 0 else "📉"
        result = ("📊 **" + name + " (" + sym + ")**\n\n"
                  "💵 " + cur + " " + "{:,.2f}".format(price) + "\n"
                  + arrow + " Change: " + "{:+.2f}".format(chg) + "%\n"
                  "📅 Prev: " + "{:,.2f}".format(prev) + "\n\n"
                  "*Live via Yahoo Finance*")
        return {"data": result, "sources": [{"title": sym, "url": "https://finance.yahoo.com/quote/" + sym, "source": "Yahoo Finance"}]}
    except Exception as e:
        # Fallback: return message asking AI to use its knowledge
        return {"data": "[PRICE_LOOKUP_FAILED] Use your knowledge to give approximate " + query + " price and mention it may not be current.", "sources": []}


# ═══════════════════════════════════════
# PHASE 4: VISION MODE (Groq LLaMA Vision)
# ═══════════════════════════════════════

async def analyze_image_vision(image_base64: str, image_type: str, question: str, api_key: str) -> dict:
    try:
        headers = {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"}
        payload = {
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "data:" + image_type + ";base64," + image_base64}},
                {"type": "text", "text": question or "Describe this image in detail."}
            ]}],
            "max_tokens": 1024, "temperature": 0.7
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
            if resp.status_code != 200:
                return {"data": "Vision error: " + resp.json().get("error", {}).get("message", "API error"), "sources": []}
            result = resp.json()["choices"][0]["message"]["content"]
        return {"data": "👁️ **Image Analysis:**\n\n" + result,
                "sources": [{"title": "Vision Analysis", "url": "#", "source": "Groq LLaMA Vision"}]}
    except Exception as e:
        return {"data": "Vision failed: " + str(e), "sources": []}

# ═══════════════════════════════════════════════════════
# PHASE 5 KEYWORDS
# ═══════════════════════════════════════════════════════
SENTIMENT_KEYWORDS = ["analyse sentiment", "analyze sentiment", "sentiment of", "what is the sentiment", "check sentiment", "detect sentiment", "sentiment analysis"]
SUMMARIZE_KEYWORDS = ["summarise", "summarize", "tldr", "tl;dr", "give me a summary", "summary of", "sum up", "brief summary", "short summary"]
CHART_KEYWORDS = ["make a chart", "create a chart", "draw a chart", "plot a graph", "make a graph", "create a graph", "bar chart", "pie chart", "line chart", "show a chart", "visualize", "visualise"]

# ═══════════════════════════════════════════════════════
# PHASE 5: SENTIMENT ANALYSIS
# ═══════════════════════════════════════════════════════
async def analyze_sentiment(text: str, hf_key: str = None) -> dict:
    """Analyze sentiment using AI."""
    # Use AI directly - HuggingFace added in Phase 6
    return {"data": "[SENTIMENT_FALLBACK]" + text, "mood": "unknown", "source": "ai"}

# ═══════════════════════════════════════════════════════
# PHASE 5: TEXT SUMMARIZER
# ═══════════════════════════════════════════════════════
async def summarize_text(text: str, hf_key: str = None) -> dict:
    """Summarize text using AI."""
    return {"data": "[SUMMARIZE_FALLBACK]" + text[:2000], "source": "ai"}

# ═══════════════════════════════════════════════════════
# PHASE 5: LANGUAGE DETECTION
# ═══════════════════════════════════════════════════════
async def detect_language(text: str, hf_key: str = None) -> dict:
    """Detect language using Unicode script detection — no API needed."""
    import unicodedata

    if not text or len(text.strip()) < 2:
        return {"language": "en", "score": 0, "source": "script"}

    # Count characters per script
    tamil = hindi = telugu = malayalam = kannada = arabic = japanese = chinese = korean = 0
    total = 0

    for ch in text:
        cp = ord(ch)
        if '\u0B80' <= ch <= '\u0BFF': tamil += 1
        elif '\u0900' <= ch <= '\u097F': hindi += 1
        elif '\u0C00' <= ch <= '\u0C7F': telugu += 1
        elif '\u0D00' <= ch <= '\u0D7F': malayalam += 1
        elif '\u0C80' <= ch <= '\u0CFF': kannada += 1
        elif '\u0600' <= ch <= '\u06FF': arabic += 1
        elif '\u3040' <= ch <= '\u30FF': japanese += 1
        elif '\u4E00' <= ch <= '\u9FFF': chinese += 1
        elif '\uAC00' <= ch <= '\uD7AF': korean += 1
        if ch.strip(): total += 1

    if total == 0:
        return {"language": "en", "score": 0, "source": "script"}

    scores = {
        "ta": tamil, "hi": hindi, "te": telugu,
        "ml": malayalam, "kn": kannada, "ar": arabic,
        "ja": japanese, "zh": chinese, "ko": korean
    }

    best_lang, best_count = max(scores.items(), key=lambda x: x[1])
    confidence = int((best_count / total) * 100)

    if confidence >= 30:
        return {"language": best_lang, "score": confidence, "source": "script"}

    return {"language": "en", "score": 0, "source": "script"}

# ═══════════════════════════════════════════════════════
# PHASE 5: CHART DATA EXTRACTOR
# ═══════════════════════════════════════════════════════
def extract_chart_query(message: str) -> str:
    """Extract chart topic from message."""
    lower = message.lower()
    for kw in ["make a chart of", "create a chart of", "plot a graph of", "make a graph of",
               "bar chart of", "pie chart of", "line chart of", "chart of", "graph of",
               "visualize", "visualise"]:
        if kw in lower:
            return message[lower.find(kw) + len(kw):].strip().rstrip("?.")
    return message

def extract_sentiment_text(message: str) -> str:
    """Extract text to analyze from message."""
    lower = message.lower()
    for kw in SENTIMENT_KEYWORDS:
        if kw in lower:
            idx = lower.find(kw) + len(kw)
            text = message[idx:].strip().lstrip(":").strip()
            return text if text else message
    return message

def extract_summary_text(message: str) -> str:
    """Extract text to summarize."""
    lower = message.lower()
    for kw in SUMMARIZE_KEYWORDS:
        if kw in lower:
            idx = lower.find(kw) + len(kw)
            text = message[idx:].strip().lstrip(":").strip()
            return text if text else message
    return message

# ═══════════════════════════════════════════════════════
# PHASE 5: AUTO TRANSLATE
# ═══════════════════════════════════════════════════════

# Language code to full name mapping
LANG_NAMES = {
    "ta": "Tamil", "hi": "Hindi", "te": "Telugu", "ml": "Malayalam",
    "kn": "Kannada", "mr": "Marathi", "bn": "Bengali", "gu": "Gujarati",
    "pa": "Punjabi", "ur": "Urdu", "fr": "French", "es": "Spanish",
    "de": "German", "it": "Italian", "pt": "Portuguese", "ru": "Russian",
    "ja": "Japanese", "ko": "Korean", "zh": "Chinese", "ar": "Arabic",
    "tr": "Turkish", "nl": "Dutch", "pl": "Polish", "sv": "Swedish",
    "en": "English"
}

TRANSLATE_KEYWORDS = ["translate", "translation of", "translate this", "in tamil", "in hindi",
                      "in french", "in spanish", "in german", "in japanese", "in korean",
                      "in chinese", "in arabic", "in telugu", "in malayalam", "in kannada"]

async def auto_detect_and_translate(message: str, hf_key: str = None) -> dict:
    """Detect language and return translation instruction for AI."""
    try:
        # Detect language using HuggingFace
        lang_result = await detect_language(message, hf_key)
        detected_lang = lang_result.get("language", "en")
        lang_name = LANG_NAMES.get(detected_lang, detected_lang.upper())
        confidence = lang_result.get("score", 0)

        if detected_lang != "en" and confidence >= 30:
            return {
                "detected": detected_lang,
                "lang_name": lang_name,
                "confidence": confidence,
                "instruction": f"The user is writing in {lang_name}. Reply ENTIRELY in {lang_name} script only. Do NOT use English. Do NOT add transliteration or romanized text in brackets. Write naturally like a native {lang_name} speaker would.",
                "non_english": True
            }
        return {"detected": "en", "lang_name": "English", "non_english": False, "instruction": ""}
    except Exception:
        return {"detected": "en", "lang_name": "English", "non_english": False, "instruction": ""}

async def translate_text(text: str, target_lang: str, hf_key: str = None) -> dict:
    """Translate text to target language."""
    target_name = LANG_NAMES.get(target_lang, target_lang)
    # Use AI for translation (most reliable for Indian languages)
    return {
        "data": f"[TRANSLATE_REQUEST]\nTranslate the following text to {target_name}:\n{text}\n\nProvide ONLY the translated text, nothing else.",
        "target": target_name,
        "source": "ai"
    }

def extract_translate_request(message: str) -> tuple:
    """Extract text and target language from translate request."""
    lower = message.lower()
    # Check for explicit translate request
    for lang_code, lang_name in LANG_NAMES.items():
        if f"translate to {lang_name.lower()}" in lower or f"in {lang_name.lower()}" in lower:
            # Extract text to translate
            text = message
            for kw in ["translate to " + lang_name.lower(), "in " + lang_name.lower(), "translate:"]:
                if kw in lower:
                    idx = lower.find(kw) + len(kw)
                    extracted = message[idx:].strip().lstrip(":").strip()
                    if extracted:
                        text = extracted
                        break
            return text, lang_code
    return message, None


# ═══════════════════════════════════════════════════════════════
# PHASE 6 — FEATURE ADDITIONS
# ═══════════════════════════════════════════════════════════════

import re as _re
import json as _json
import urllib.parse as _urlparse

# ── Keywords ──
REPORT_KEYWORDS   = ["generate report", "create report", "make report", "write report",
                     "research report", "detailed report", "full report"]
PDF_KEYWORDS      = ["convert to pdf", "save as pdf", "export pdf", "download pdf",
                     "make pdf", "create pdf", "as a pdf"]
DOCX_KEYWORDS     = ["convert to word", "save as word", "export word", "download word",
                     "make word", "create word", "as a word", "as a doc", "docx"]
NOTE_KEYWORDS     = ["save note", "remember this", "note this", "save this",
                     "keep note", "take note", "note down", "remember that"]
RECALL_KEYWORDS   = ["show notes", "my notes", "what did i save", "recall notes",
                     "show my notes", "list notes", "get notes"]
TODO_KEYWORDS     = ["add task", "add to do", "add todo", "remind me to",
                     "create task", "new task", "set reminder", "remind me at",
                     "add reminder", "schedule reminder"]
SHOW_TODO_KEYWORDS = ["show tasks", "my tasks", "show todos", "pending tasks",
                      "list tasks", "what are my tasks", "show reminders"]
DONE_TODO_KEYWORDS = ["mark done", "complete task", "task done", "finished task",
                      "mark as done", "mark complete"]
RESUME_KEYWORDS   = ["build resume", "create resume", "make resume", "generate resume",
                     "write resume", "build my resume", "create my resume"]

# ── Meme templates (memegen.link) ──




# ── Note storage helpers ──
def format_note_instruction(message: str) -> str:
    """Tell AI to save a note."""
    return f"""[NOTE_SAVE_REQUEST]
The user wants to save this note: {message}
Respond with: "Got it! ✅ I've saved your note: [note content]"
Then output: [NOTE_SAVED]: <the note text>
"""

def format_recall_instruction() -> str:
    return "[NOTE_RECALL_REQUEST]\nThe user wants to see their saved notes.\nRespond: 'Here are your saved notes:' and list them."

# ── Todo helpers ──
def format_todo_instruction(message: str) -> str:
    return f"""[TODO_ADD_REQUEST]
The user wants to add a task or reminder: {message}
Extract: task description and time if mentioned (e.g. "at 6pm", "tomorrow", "in 2 hours").
Respond: "Added to your tasks! ✅ I'll remind you: [task]. [time if given]"
Then output: [TODO_ADDED]: <task> | <time_string or 'no_time'>
"""

def format_show_todos_instruction() -> str:
    return "[TODO_SHOW_REQUEST]\nThe user wants to see their tasks. Output: [TODO_LIST_REQUEST]"

def format_done_todo_instruction(message: str) -> str:
    return f"[TODO_DONE_REQUEST]\nUser completed: {message}\nOutput: [TODO_DONE]: <task keyword>"

# ── Google Calendar quick link ──
def generate_calendar_link(title: str, details: str = "", start: str = "", end: str = "") -> str:
    base = "https://calendar.google.com/calendar/render?action=TEMPLATE"
    params = f"&text={_urlparse.quote(title)}"
    if details: params += f"&details={_urlparse.quote(details)}"
    if start: params += f"&dates={start}/{end or start}"
    return base + params

# ── Resume keywords ──
RESUME_STAGES = ["name", "title", "email", "phone", "skills", "experience", "education", "achievements", "photo"]

def format_resume_instruction(stage: str, data: dict) -> str:
    collected = _json.dumps(data, indent=2)
    if stage == "start":
        return f"""[RESUME_BUILD_START]
Start building the user's resume. Ask for their full name first.
Say: "Let's build your resume! 📄 I'll ask you a few questions.
First, what's your full name?"
Output: [RESUME_STAGE]: name"""
    elif stage == "generate":
        return f"""[RESUME_GENERATE]
Generate a professional resume PDF and Word document for:
{collected}
Say: "Your resume is ready! 🎉 Downloading now..."
Output: [RESUME_READY]: {collected}"""
    return ""

