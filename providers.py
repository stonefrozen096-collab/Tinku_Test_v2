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


CODE_KEYWORDS = ["run this code", "execute this", "run this python", "execute python",
    "run the code", "execute the code", "run code", "test this code", "execute this code"]

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
    """Detect which tools are needed — Phase 3."""
    lower = message.lower()
    tools = {
        "weather": False, "search": False, "currency": False, "report": False,
        "url": False, "file": False, "code": False,
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

def extract_url_from_message(message: str) -> Optional[str]:
    """Extract URL from user message."""
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    match = re.search(url_pattern, message)
    if match:
        return match.group(0)
    # Also check for www. URLs without protocol
    www_pattern = r'www\.[^\s<>"{}|\\^`\[\]]+'
    match = re.search(www_pattern, message)
    if match:
        return "https://" + match.group(0)
    return None


# ═══════════════════════════════════════
# HELPER: Extract code from message
# ═══════════════════════════════════════

def extract_code_from_message(message: str) -> Optional[str]:
    """Extract code block from user message."""
    # Look for ```python ... ``` or ``` ... ```
    patterns = [
        r'```python\s*([\s\S]+?)```',
        r'```\s*([\s\S]+?)```',
        r'`([^`]+)`',
    ]
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None
