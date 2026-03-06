"""
Chat Router — Tinku Agent Phase 2
Features: Thinking steps, source links, report generation, GNews
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
import json
import os
HF_KEY = os.getenv("HUGGINGFACE_API_KEY", "")
from datetime import datetime

from database import (get_db, save_conversation, save_message,
                      update_user_stats, flag_message)
from providers import (generate_response, check_content, PROVIDERS,
                       detect_tools_needed, get_weather, web_search,
                       get_exchange_rate, build_report_prompt,
                       fetch_url_content, analyze_file, execute_code,
                       extract_code_from_message,
                       search_song, extract_song_query,
                       get_stock_price, extract_stock_query,
                       analyze_image_vision,
                       analyze_sentiment, summarize_text, detect_language,
                       extract_sentiment_text, extract_summary_text, extract_chart_query,
                       auto_detect_and_translate, translate_text, extract_translate_request, LANG_NAMES)
from routers.auth import get_current_user

router = APIRouter()


class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    memory_context: str = ""
    history: List[Message] = []
    provider: str = "gemini"
    model: str = "gemini-2.0-flash"
    api_key: str
    conversation_id: Optional[str] = None
    file_content: Optional[str] = None
    file_name: Optional[str] = None
    image_base64: Optional[str] = None
    image_type: Optional[str] = None
    image_question: Optional[str] = None
    hf_key: Optional[str] = None


def step_event(emoji: str, text: str, status: str = "running") -> str:
    """Create a thinking step SSE event."""
    return f"data: {json.dumps({'type': 'step', 'emoji': emoji, 'text': text, 'status': status})}\n\n"

def sources_event(sources: list) -> str:
    """Send sources to frontend."""
    return f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"


@router.post("/send")
async def send_message(data: ChatRequest, request: Request, db=Depends(get_db)):
    user = get_current_user(request)
    user_id = user["user_id"] if user else "guest"
    is_guest = not user or user.get("is_guest", False)

    is_flagged, flag_reason = check_content(data.message)
    messages = [{"role": m.role, "content": m.content} for m in data.history]
    messages.append({"role": "user", "content": data.message})

    conv_id = data.conversation_id
    if not is_guest and not conv_id:
        title = data.message[:50] + ("..." if len(data.message) > 50 else "")
        conv_id = await save_conversation(db, user_id, title, data.model, data.provider)

    if not is_guest:
        await save_message(db, conv_id, user_id, "user", data.message,
                          flagged=is_flagged, flag_reason=flag_reason)

    async def stream():
        full_response = ""
        all_sources = []
        tool_context = ""

        try:
            # ── STEP 1: Analyze ──
            yield step_event("🤔", "Analyzing your question...", "running")
            has_file = bool(data.file_content and data.file_name)
            tools = detect_tools_needed(data.message, has_file=has_file)
            has_image = bool(data.image_base64)
            if has_image: tools["vision"] = True
            needs_tools = (tools["weather"] or tools["search"] or tools["currency"]
                          or tools["report"] or tools["url"] or tools["file"] or tools["code"]
                          or tools["song"] or tools["stock"] or tools["research"] or tools["vision"]
                          or tools["sentiment"] or tools["summarize"] or tools["chart"] or tools["translate"])

            # ── STEP 2: Run Tools ──
            if tools["report"]:
                yield step_event("🤔", "Analyzing your question...", "done")
                yield step_event("📊", "Planning report structure...", "running")

                # Clean topic — remove report keywords AND memory context
                import re as re_mod
                topic = data.message
                # Strip memory context first
                topic = re_mod.sub(r'\[Memory about user:[^\]]*\]', '', topic, flags=re_mod.IGNORECASE)
                topic = re_mod.sub(r'\[MEMORY ABOUT USER:[^\]]*\]', '', topic, flags=re_mod.IGNORECASE)
                topic = topic.lower()
                for kw in ["prepare a report", "generate a report", "make a report",
                           "write a report", "create a report", "report on", "report about",
                           "detailed report", "comprehensive report", "full report"]:
                    topic = topic.replace(kw, "").strip()
                topic = re_mod.sub(r'[?.,!\s]+$', '', topic).strip()
                if not topic:
                    topic = "the requested topic"

                yield step_event("📊", "Planning report structure...", "done")
                yield step_event("🔍", f"Researching '{topic}'...", "running")
                search_result = await web_search(topic)
                tool_context += f"\n\n[RESEARCH DATA]\n{search_result['data']}\n"
                all_sources.extend(search_result.get("sources", []))
                yield step_event("🔍", f"Researching '{topic}'...", "done")

                yield step_event("✍️", "Writing report...", "running")
                # Replace last user message with report prompt
                messages[-1] = {
                    "role": "user",
                    "content": build_report_prompt(topic, search_result['data'])
                }
                yield step_event("✍️", "Writing report...", "done")

            else:
                if needs_tools:
                    yield step_event("🤔", "Analyzing your question...", "done")
                    yield step_event("⚙️", "Selecting tools...", "running")
                    yield step_event("⚙️", "Selecting tools...", "done")

                if tools["weather"]:
                    city = tools["city"] or "Mumbai"
                    yield step_event("🌤", f"Fetching live weather for {city}...", "running")
                    weather_result = await get_weather(city)
                    tool_context += f"\n\n[LIVE WEATHER DATA]\n{weather_result['data']}\n"
                    all_sources.extend(weather_result.get("sources", []))
                    yield step_event("🌤", f"Fetching live weather for {city}...", "done")

                if tools["search"]:
                    yield step_event("🔍", "Searching the web...", "running")
                    search_result = await web_search(data.message)
                    tool_context += f"\n\n[WEB SEARCH RESULTS]\n{search_result['data']}\n"
                    all_sources.extend(search_result.get("sources", []))
                    yield step_event("🔍", "Searching the web...", "done")

                if tools["currency"]:
                    yield step_event("💱", "Fetching live exchange rates...", "running")
                    currency_result = await get_exchange_rate()
                    tool_context += f"\n\n[LIVE EXCHANGE RATES]\n{currency_result['data']}\n"
                    all_sources.extend(currency_result.get("sources", []))
                    yield step_event("💱", "Fetching live exchange rates...", "done")

                if tools["url"] and tools["url_value"]:
                    yield step_event("🔗", "Reading URL content...", "running")
                    url_result = await fetch_url_content(tools["url_value"])
                    tool_context += f"\n\n[URL CONTENT]\n{url_result['data']}\n"
                    all_sources.extend(url_result.get("sources", []))
                    yield step_event("🔗", "Reading URL content...", "done")

                if tools["file"] and data.file_content:
                    yield step_event("📁", f"Analyzing {data.file_name}...", "running")
                    file_result = await analyze_file(data.file_content, data.file_name)
                    tool_context += f"\n\n[FILE CONTENT]\n{file_result['data']}\n"
                    all_sources.extend(file_result.get("sources", []))
                    yield step_event("📁", f"Analyzing {data.file_name}...", "done")

                if tools["code"]:
                    code = extract_code_from_message(data.message)
                    if code:
                        yield step_event("💻", "Executing code...", "running")
                        code_result = await execute_code(code)
                        tool_context += f"\n\n[CODE OUTPUT]\n{code_result['data']}\n"
                        all_sources.extend(code_result.get("sources", []))
                        yield step_event("💻", "Executing code...", "done")
                        yield f"data: {json.dumps({'type': 'code_result', 'output': code_result.get('output',''), 'full': code_result['data']})}\n\n"

                # Phase 4: Song Finder
                if tools["song"]:
                    q = extract_song_query(data.message)
                    yield step_event("🎵", "Searching songs...", "running")
                    sr = await search_song(q)
                    tool_context += "\n\n[SONG RESULTS]\n" + sr["data"] + "\n"
                    all_sources.extend(sr.get("sources", []))
                    yield step_event("🎵", "Searching songs...", "done")
                    # Songs sent via sources event (more reliable)
                    if sr.get("songs"):
                        all_sources = [{"type": "song", "song": s} for s in sr["songs"]] + all_sources

                # Phase 4: Stock/Crypto
                if tools["stock"]:
                    q = extract_stock_query(data.message)
                    yield step_event("📈", "Fetching live price...", "running")
                    stk = await get_stock_price(q)
                    tool_context += "\n\n[PRICE DATA]\n" + stk["data"] + "\n"
                    all_sources.extend(stk.get("sources", []))
                    yield step_event("📈", "Fetching live price...", "done")

                # Phase 4: Vision Mode
                if tools["vision"] and data.image_base64:
                    yield step_event("👁️", "Analyzing image...", "running")
                    vis = await analyze_image_vision(
                        data.image_base64, data.image_type or "image/jpeg",
                        data.image_question or data.message, data.api_key
                    )
                    tool_context += "\n\n[IMAGE ANALYSIS]\n" + vis["data"] + "\n"
                    all_sources.extend(vis.get("sources", []))
                    yield step_event("👁️", "Analyzing image...", "done")

                # Phase 5: Sentiment Analysis
                if tools["sentiment"]:
                    text = extract_sentiment_text(data.message)
                    yield step_event("😊", "Analysing sentiment...", "running")
                    hf = HF_KEY or data.hf_key or ""
                    sent = await analyze_sentiment(text, hf)
                    if sent["source"] == "ai":
                        tool_context += f"\n\n[SENTIMENT ANALYSIS]\nAnalyse the sentiment of this text and reply with: emoji, label (Positive/Negative/Neutral), confidence %, and a mood-appropriate response. Text: {text}\n"
                    else:
                        tool_context += f"\n\n[SENTIMENT RESULT]\n{sent['data']}\nMood: {sent['mood']}\nNow respond in a tone matching this mood.\n"
                    yield step_event("😊", "Analysing sentiment...", "done")
                    yield "data: " + json.dumps({"type": "sentiment", "mood": sent.get("mood","neutral")}) + "\n\n"

                # Phase 5: Text Summarizer
                if tools["summarize"]:
                    text = extract_summary_text(data.message)
                    yield step_event("📝", "Summarising text...", "running")
                    hf = HF_KEY or data.hf_key or ""
                    summ = await summarize_text(text, hf)
                    if summ["source"] == "ai":
                        tool_context += f"\n\n[SUMMARIZE REQUEST]\nPlease summarize the following text in 3-5 clear bullet points:\n{text[:2000]}\n"
                    else:
                        tool_context += f"\n\n[SUMMARY RESULT]\n{summ['data']}\n"
                    yield step_event("📝", "Summarising text...", "done")

                # Phase 5: Charts
                if tools["chart"]:
                    chart_topic = extract_chart_query(data.message)
                    yield step_event("📊", "Preparing chart data...", "running")
                    tool_context += f"\n\n[CHART REQUEST]\nGenerate chart data for: {chart_topic}\nRespond with ONLY a JSON object in this exact format (no other text):\n{{\"type\": \"bar\" or \"pie\" or \"line\", \"title\": \"Chart Title\", \"labels\": [\"A\",\"B\",\"C\"], \"data\": [10,20,30], \"colors\": [\"#6366f1\",\"#8b5cf6\",\"#06b6d4\"]}}\n"
                    yield step_event("📊", "Preparing chart data...", "done")

                # Phase 5: Auto Translate
                if tools["translate"]:
                    hf = HF_KEY or data.hf_key or ""
                    text, target_lang = extract_translate_request(data.message)
                    if target_lang:
                        # Explicit translate request
                        yield step_event("🌍", f"Translating to {LANG_NAMES.get(target_lang, target_lang)}...", "running")
                        tr = await translate_text(text, target_lang, hf)
                        tool_context += f"\n\n{tr['data']}\n"
                        yield step_event("🌍", f"Translating...", "done")
                    else:
                        # Auto detect language and reply in same language
                        yield step_event("🌍", "Detecting language...", "running")
                        lang_info = await auto_detect_and_translate(data.message, hf)
                        if lang_info["non_english"]:
                            tool_context += f"\n\n[LANGUAGE INSTRUCTION]\n{lang_info['instruction']}\n"
                            yield step_event("🌍", f"Replying in {lang_info['lang_name']}...", "done")
                        else:
                            yield step_event("🌍", "Detecting language...", "done")

                if not needs_tools:
                    yield step_event("🤔", "Analyzing your question...", "done")

            yield step_event("✨", "Generating response...", "running")

            # ── Build final messages with memory as system context ──
            final_messages = messages.copy()

            # Memory goes into system prompt silently — NOT into user message
            memory_instruction = ""
            if data.memory_context and not tools["report"]:
                memory_instruction = (
                    f"\n\n[SILENT CONTEXT — Do NOT greet user by name, do NOT mention this memory, "
                    f"do NOT say 'Hello Hari' or reference the user's name in responses. "
                    f"Use this only as background context if directly relevant: {data.memory_context}]"
                )
            # Auto sentiment — always detect mood and adjust tone silently
            if not tools["sentiment"] and not tools["report"]:
                msg_lower = data.message.lower()
                if any(w in msg_lower for w in ["sad", "cry", "failed", "fail", "depressed", "lonely", "hurt", "pain", "miss", "heartbreak", "broke up", "scared", "afraid", "worried", "anxious", "stressed"]):
                    memory_instruction += "\n\n[MOOD: User seems sad/stressed. Reply with empathy, warmth and support. Use 💙 tone.]"
                elif any(w in msg_lower for w in ["happy", "excited", "amazing", "awesome", "love", "great", "wonderful", "fantastic", "yay", "won", "passed", "got", "promoted", "congrat"]):
                    memory_instruction += "\n\n[MOOD: User seems happy/excited. Match their energy! Be enthusiastic and celebratory 🎉]"
                elif any(w in msg_lower for w in ["angry", "hate", "frustrated", "annoyed", "stupid", "idiot", "worst", "terrible", "awful"]):
                    memory_instruction += "\n\n[MOOD: User seems frustrated/angry. Be calm, patient and understanding. De-escalate gently 😌]"

            if tool_context and not tools["report"]:
                final_messages[-1] = {
                    "role": "user",
                    "content": data.message + tool_context +
                               "\n\n[Use the above real-time data to answer accurately and helpfully.]"
                }
            # memory_instruction is passed separately to generate_response

            # ── Flagged warning ──
            if is_flagged:
                warning = "⚠️ Your message was flagged for review.\n\n"
                yield f"data: {json.dumps({'type': 'chunk', 'text': warning})}\n\n"
                full_response += warning

            # ── Stream AI Response ──
            async for chunk in generate_response(
                final_messages, data.provider, data.model,
                data.api_key, memory_instruction
            ):
                full_response += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"

            yield step_event("✨", "Generating response...", "done")

            # ── Send sources ──
            if all_sources:
                yield sources_event(all_sources)

            # ── Report download flag ──
            if tools["report"]:
                yield f"data: {json.dumps({'type': 'report', 'content': full_response})}\n\n"

            # ── Save to DB ──
            if not is_guest and conv_id:
                resp_flagged, resp_reason = check_content(full_response)
                await save_message(db, conv_id, user_id, "assistant", full_response,
                                  flagged=resp_flagged, flag_reason=resp_reason)
                await update_user_stats(db, user_id, data.provider, data.model)

            yield f"data: {json.dumps({'type': 'done', 'conversation_id': conv_id or ''})}\n\n"

        except Exception as e:
            import traceback
            err_detail = traceback.format_exc()
            print("STREAM ERROR:", err_detail)
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.get("/conversations")
async def get_conversations(request: Request, db=Depends(get_db)):
    user = get_current_user(request)
    if not user or user.get("is_guest"):
        return {"conversations": []}
    convos = await db.conversations.find(
        {"user_id": user["user_id"]}
    ).sort("updated_at", -1).limit(50).to_list(50)
    return {"conversations": [
        {"id": str(c["_id"]), "title": c["title"], "model": c.get("model", ""),
         "provider": c.get("provider", ""), "message_count": c.get("message_count", 0),
         "updated_at": c["updated_at"].isoformat()}
        for c in convos
    ]}


@router.get("/conversations/{conv_id}/messages")
async def get_messages(conv_id: str, request: Request, db=Depends(get_db)):
    user = get_current_user(request)
    if not user or user.get("is_guest"):
        raise HTTPException(status_code=401, detail="Login required")
    from bson import ObjectId
    conv = await db.conversations.find_one({"_id": ObjectId(conv_id), "user_id": user["user_id"]})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    msgs = await db.messages.find({"conversation_id": conv_id}).sort("created_at", 1).to_list(500)
    return {"messages": [
        {"id": str(m["_id"]), "role": m["role"], "content": m["content"],
         "created_at": m["created_at"].isoformat(), "flagged": m.get("flagged", False)}
        for m in msgs
    ]}


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str, request: Request, db=Depends(get_db)):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    from bson import ObjectId
    await db.conversations.delete_one({"_id": ObjectId(conv_id), "user_id": user["user_id"]})
    await db.messages.delete_many({"conversation_id": conv_id})
    return {"success": True}


@router.get("/providers")
async def get_providers():
    return {"providers": PROVIDERS}


# PHASE 3: FILE UPLOAD ENDPOINT
from fastapi import UploadFile, File

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Accept file uploads for analysis."""
    ALLOWED = {"txt","csv","json","py","md","js","html","css"}
    ext = file.filename.lower().split(".")[-1] if "." in file.filename else ""
    if ext not in ALLOWED:
        raise HTTPException(status_code=400, detail=f"File type .{ext} not supported.")
    data = await file.read()
    if len(data) > 500*1024:
        raise HTTPException(status_code=400, detail="File too large. Max 500KB.")
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError:
        content = data.decode("latin-1")
    return {"success":True,"file_name":file.filename,"file_size":len(data),"content":content,"preview":content[:200]}
