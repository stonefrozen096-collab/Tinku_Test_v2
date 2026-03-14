"""
Chat Router — Tinku Agent Phase 8
Features: ReAct Agent Loop (Reasoning + Acting), Thinking steps, source links, report generation, GNews
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
from memory import (extract_facts, save_memory, get_memories,
                    save_topic, get_recent_topics, format_memory_context,
                    get_memory_summary)

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


# ════════════════════════════════════════
# PHASE 8: ReAct Tool Runner
# Runs tools based on detected needs and returns context + sources
# ════════════════════════════════════════
async def run_tools(tools: dict, data: ChatRequest, messages: list):
    """
    ReAct ACT phase — runs all needed tools and returns:
    - tool_context: string of all tool results
    - all_sources: list of sources
    - step_events: list of SSE step events to yield
    - updated messages (for report mode)
    """
    tool_context = ""
    all_sources = []
    step_events = []
    import re as re_mod

    # ── Report ──
    if tools["report"]:
        step_events.append(step_event("📊", "Planning report structure...", "running"))

        topic = data.message
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

        step_events.append(step_event("📊", "Planning report structure...", "done"))
        step_events.append(step_event("🔍", f"Researching '{topic}'...", "running"))

        search_result = await web_search(topic)
        tool_context += f"\n\n[RESEARCH DATA]\n{search_result['data']}\n"
        all_sources.extend(search_result.get("sources", []))

        step_events.append(step_event("🔍", f"Researching '{topic}'...", "done"))
        step_events.append(step_event("✍️", "Writing report...", "running"))

        messages[-1] = {
            "role": "user",
            "content": build_report_prompt(topic, search_result['data'])
        }
        step_events.append(step_event("✍️", "Writing report...", "done"))

    else:
        # ── Weather ──
        if tools["weather"]:
            city = tools["city"] or "Mumbai"
            step_events.append(step_event("🌤", f"Fetching live weather for {city}...", "running"))
            weather_result = await get_weather(city)
            tool_context += f"\n\n[LIVE WEATHER DATA]\n{weather_result['data']}\n"
            all_sources.extend(weather_result.get("sources", []))
            step_events.append(step_event("🌤", f"Fetching live weather for {city}...", "done"))

        # ── Web Search ──
        if tools["search"]:
            step_events.append(step_event("🔍", "Searching the web...", "running"))
            search_result = await web_search(data.message)
            tool_context += f"\n\n[WEB SEARCH RESULTS]\n{search_result['data']}\n"
            all_sources.extend(search_result.get("sources", []))
            step_events.append(step_event("🔍", "Searching the web...", "done"))

        # ── Currency ──
        if tools["currency"]:
            step_events.append(step_event("💱", "Fetching live exchange rates...", "running"))
            currency_result = await get_exchange_rate()
            tool_context += f"\n\n[LIVE EXCHANGE RATES]\n{currency_result['data']}\n"
            all_sources.extend(currency_result.get("sources", []))
            step_events.append(step_event("💱", "Fetching live exchange rates...", "done"))

        # ── URL ──
        if tools["url"] and tools["url_value"]:
            step_events.append(step_event("🔗", "Reading URL content...", "running"))
            url_result = await fetch_url_content(tools["url_value"])
            tool_context += f"\n\n[URL CONTENT]\n{url_result['data']}\n"
            all_sources.extend(url_result.get("sources", []))
            step_events.append(step_event("🔗", "Reading URL content...", "done"))

        # ── File ──
        if tools["file"] and data.file_content:
            step_events.append(step_event("📁", f"Analyzing {data.file_name}...", "running"))
            file_result = await analyze_file(data.file_content, data.file_name)
            tool_context += f"\n\n[FILE CONTENT]\n{file_result['data']}\n"
            all_sources.extend(file_result.get("sources", []))
            step_events.append(step_event("📁", f"Analyzing {data.file_name}...", "done"))

        # ── Code ──
        if tools["code"]:
            code = extract_code_from_message(data.message)
            if code:
                step_events.append(step_event("💻", "Executing code...", "running"))
                code_result = await execute_code(code)
                tool_context += f"\n\n[CODE OUTPUT]\n{code_result['data']}\n"
                all_sources.extend(code_result.get("sources", []))
                step_events.append(step_event("💻", "Executing code...", "done"))

        # ── Song ──
        if tools["song"]:
            q = extract_song_query(data.message)
            step_events.append(step_event("🎵", "Searching songs...", "running"))
            sr = await search_song(q)
            tool_context += "\n\n[SONG RESULTS]\n" + sr["data"] + "\n"
            all_sources.extend(sr.get("sources", []))
            step_events.append(step_event("🎵", "Searching songs...", "done"))
            if sr.get("songs"):
                all_sources = [{"type": "song", "song": s} for s in sr["songs"]] + all_sources

        # ── Stock ──
        if tools["stock"]:
            q = extract_stock_query(data.message)
            step_events.append(step_event("📈", "Fetching live price...", "running"))
            stk = await get_stock_price(q)
            tool_context += "\n\n[PRICE DATA]\n" + stk["data"] + "\n"
            all_sources.extend(stk.get("sources", []))
            step_events.append(step_event("📈", "Fetching live price...", "done"))

        # ── Vision ──
        if tools["vision"] and data.image_base64:
            step_events.append(step_event("👁️", "Analyzing image...", "running"))
            vis = await analyze_image_vision(
                data.image_base64, data.image_type or "image/jpeg",
                data.image_question or data.message, data.api_key
            )
            tool_context += "\n\n[IMAGE ANALYSIS]\n" + vis["data"] + "\n"
            all_sources.extend(vis.get("sources", []))
            step_events.append(step_event("👁️", "Analyzing image...", "done"))

        # ── Sentiment ──
        if tools["sentiment"]:
            text = extract_sentiment_text(data.message)
            step_events.append(step_event("😊", "Analysing sentiment...", "running"))
            hf = HF_KEY or data.hf_key or ""
            sent = await analyze_sentiment(text, hf)
            if sent["source"] == "ai":
                tool_context += f"\n\n[SENTIMENT ANALYSIS]\nAnalyse the sentiment of this text and reply with: emoji, label (Positive/Negative/Neutral), confidence %, and a mood-appropriate response. Text: {text}\n"
            else:
                tool_context += f"\n\n[SENTIMENT RESULT]\n{sent['data']}\nMood: {sent['mood']}\nNow respond in a tone matching this mood.\n"
            step_events.append(step_event("😊", "Analysing sentiment...", "done"))

        # ── Summarize ──
        if tools["summarize"]:
            text = extract_summary_text(data.message)
            step_events.append(step_event("📝", "Summarising text...", "running"))
            hf = HF_KEY or data.hf_key or ""
            summ = await summarize_text(text, hf)
            if summ["source"] == "ai":
                tool_context += f"\n\n[SUMMARIZE REQUEST]\nPlease summarize the following text in 3-5 clear bullet points:\n{text[:2000]}\n"
            else:
                tool_context += f"\n\n[SUMMARY RESULT]\n{summ['data']}\n"
            step_events.append(step_event("📝", "Summarising text...", "done"))

        # ── Chart ──
        if tools["chart"]:
            chart_topic = extract_chart_query(data.message)
            step_events.append(step_event("📊", "Preparing chart data...", "running"))
            tool_context += f"\n\n[CHART REQUEST]\nGenerate chart data for: {chart_topic}\nRespond with ONLY a JSON object in this exact format (no other text):\n{{\"type\": \"bar\" or \"pie\" or \"line\", \"title\": \"Chart Title\", \"labels\": [\"A\",\"B\",\"C\"], \"data\": [10,20,30], \"colors\": [\"#6366f1\",\"#8b5cf6\",\"#06b6d4\"]}}\n"
            step_events.append(step_event("📊", "Preparing chart data...", "done"))

        # ── Translate ──
        if tools["translate"]:
            hf = HF_KEY or data.hf_key or ""
            text, target_lang = extract_translate_request(data.message)
            if target_lang:
                step_events.append(step_event("🌍", f"Translating to {LANG_NAMES.get(target_lang, target_lang)}...", "running"))
                tr = await translate_text(text, target_lang, hf)
                tool_context += f"\n\n{tr['data']}\n"
                step_events.append(step_event("🌍", "Translating...", "done"))
            else:
                step_events.append(step_event("🌍", "Detecting language...", "running"))
                lang_info = await auto_detect_and_translate(data.message, hf)
                if lang_info["non_english"]:
                    tool_context += f"\n\n[LANGUAGE INSTRUCTION]\n{lang_info['instruction']}\n"
                    step_events.append(step_event("🌍", f"Replying in {lang_info['lang_name']}...", "done"))
                else:
                    step_events.append(step_event("🌍", "Detecting language...", "done"))

        # ── Phase 6 Tools ──
        if tools["note_save"]:
            step_events.append(step_event("📝", "Saving note...", "running"))
            tool_context += f"\n\n{format_note_instruction(data.message)}"
            step_events.append(step_event("📝", "Note saved!", "done"))

        if tools["note_recall"]:
            step_events.append(step_event("📝", "Fetching your notes...", "running"))
            tool_context += f"\n\n{format_recall_instruction()}"
            step_events.append(step_event("📝", "Notes loaded!", "done"))

        if tools["todo_add"]:
            step_events.append(step_event("✅", "Adding to your tasks...", "running"))
            tool_context += f"\n\n{format_todo_instruction(data.message)}"
            step_events.append(step_event("✅", "Task added!", "done"))

        if tools["todo_show"]:
            step_events.append(step_event("✅", "Loading your tasks...", "running"))
            tool_context += f"\n\n{format_show_todos_instruction()}"
            step_events.append(step_event("✅", "Tasks loaded!", "done"))

        if tools["todo_done"]:
            step_events.append(step_event("✅", "Marking task done...", "running"))
            tool_context += f"\n\n{format_done_todo_instruction(data.message)}"
            step_events.append(step_event("✅", "Task completed!", "done"))

        if tools["pdf_export"] or tools["docx_export"]:
            fmt = "PDF" if tools["pdf_export"] else "Word"
            step_events.append(step_event("📄", f"Preparing {fmt} export...", "running"))
            tool_context += f"\n\n[FILE_EXPORT_REQUEST]\nThe user wants to export content as {fmt}. Generate the content beautifully formatted. Output: [EXPORT_FORMAT]: {fmt.lower()}"
            step_events.append(step_event("📄", f"{fmt} export ready!", "done"))

        if tools["resume"]:
            step_events.append(step_event("📄", "Starting resume builder...", "running"))
            tool_context += f"\n\n[RESUME_BUILD]\nStart building a professional resume. Ask for name first. Output: [RESUME_START]"
            step_events.append(step_event("📄", "Resume builder ready!", "done"))

    return tool_context, all_sources, step_events, messages


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

    # ── Phase 9: Load memories from DB ──
    db_memories = {}
    db_topics = []
    if not is_guest:
        db_memories = await get_memories(db, user_id)
        db_topics   = await get_recent_topics(db, user_id, limit=5)

    async def stream():
        full_response = ""
        all_sources = []
        tool_context = ""

        try:
            # ════════════════════════════════════════
            # PHASE 8: ReAct Loop
            # Max 3 iterations: THINK → ACT → OBSERVE → THINK → ANSWER
            # ════════════════════════════════════════
            MAX_ITERATIONS = 3
            iteration = 0
            react_context = ""   # Accumulates observations across iterations
            final_messages = messages.copy()

            # ── THINK: Analyze question ──
            yield step_event("🤔", "Analyzing your question...", "running")
            has_file = bool(data.file_content and data.file_name)
            tools = detect_tools_needed(data.message, has_file=has_file)
            has_image = bool(data.image_base64)
            if has_image:
                tools["vision"] = True

            needs_tools = any([
                tools["weather"], tools["search"], tools["currency"],
                tools["report"], tools["url"], tools["file"], tools["code"],
                tools["song"], tools["stock"], tools["research"], tools["vision"],
                tools["sentiment"], tools["summarize"], tools["chart"], tools["translate"],
                tools["pdf_export"], tools["docx_export"],
                tools["note_save"], tools["note_recall"],
                tools["todo_add"], tools["todo_show"], tools["todo_done"],
                tools["resume"]
            ])

            yield step_event("🤔", "Analyzing your question...", "done")

            # ── ReAct Loop ──
            while iteration < MAX_ITERATIONS:
                iteration += 1

                # If no tools needed, skip to answer immediately
                if not needs_tools:
                    break

                # ── ACT: Run tools ──
                if iteration == 1:
                    yield step_event("⚙️", "Selecting tools...", "running")
                    yield step_event("⚙️", "Selecting tools...", "done")

                tool_context, new_sources, step_events, final_messages = await run_tools(
                    tools, data, final_messages
                )
                all_sources.extend(new_sources)

                # Yield all step events from tools
                for evt in step_events:
                    yield evt

                # ── OBSERVE: Accumulate results ──
                react_context += tool_context

                # ── THINK: Do we need another iteration? ──
                # Check if the tool results mention uncertainty or need more data
                needs_more = (
                    iteration < MAX_ITERATIONS and
                    not tools["report"] and  # Reports always single pass
                    tool_context and
                    any(phrase in tool_context.lower() for phrase in [
                        "not found", "no results", "error fetching",
                        "unavailable", "could not", "failed to"
                    ])
                )

                if needs_more:
                    # Try a web search as fallback on iteration 2
                    yield step_event("🔄", f"Refining search (attempt {iteration+1})...", "running")
                    fallback = await web_search(data.message)
                    react_context += f"\n\n[FALLBACK SEARCH]\n{fallback['data']}\n"
                    all_sources.extend(fallback.get("sources", []))
                    yield step_event("🔄", f"Refining search (attempt {iteration+1})...", "done")
                else:
                    break  # Good enough, proceed to answer

            # ── BUILD FINAL MESSAGES ──
            memory_instruction = ""
            if not tools["report"]:
                # Merge frontend memory_context with DB memories
                db_mem_str = format_memory_context(db_memories, db_topics)
                combined_memory = ""
                if db_mem_str:
                    combined_memory += db_mem_str
                if data.memory_context:
                    combined_memory += "\n" + data.memory_context
                if combined_memory.strip():
                    memory_instruction = (
                        f"\n\n[SILENT CONTEXT — Do NOT greet user by name, do NOT mention this memory explicitly, "
                        f"do NOT say their name in responses unless they asked. "
                        f"Use this only as background context if directly relevant:\n{combined_memory.strip()}]"
                    )

            # Auto sentiment detection
            if not tools["sentiment"] and not tools["report"]:
                msg_lower = data.message.lower()
                if any(w in msg_lower for w in ["sad", "cry", "failed", "fail", "depressed", "lonely", "hurt", "pain", "miss", "heartbreak", "broke up", "scared", "afraid", "worried", "anxious", "stressed"]):
                    memory_instruction += "\n\n[MOOD: User seems sad/stressed. Reply with empathy, warmth and support. Use 💙 tone.]"
                elif any(w in msg_lower for w in ["happy", "excited", "amazing", "awesome", "love", "great", "wonderful", "fantastic", "yay", "won", "passed", "got", "promoted", "congrat"]):
                    memory_instruction += "\n\n[MOOD: User seems happy/excited. Match their energy! Be enthusiastic and celebratory 🎉]"
                elif any(w in msg_lower for w in ["angry", "hate", "frustrated", "annoyed", "stupid", "idiot", "worst", "terrible", "awful"]):
                    memory_instruction += "\n\n[MOOD: User seems frustrated/angry. Be calm, patient and understanding. De-escalate gently 😌]"

            # Inject all accumulated tool context into final message
            if react_context and not tools["report"]:
                final_messages[-1] = {
                    "role": "user",
                    "content": data.message + react_context +
                               "\n\n[Use the above real-time data to answer accurately and helpfully.]"
                }

            yield step_event("✨", "Generating response...", "running")

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

            # ── Send sources (deduplicated) ──
            if all_sources:
                seen = set()
                unique_sources = []
                for s in all_sources:
                    key = s.get("url") or s.get("title") or str(s)
                    if key not in seen:
                        seen.add(key)
                        unique_sources.append(s)
                yield sources_event(unique_sources)

            # ── Report download flag ──
            if tools["report"]:
                yield f"data: {json.dumps({'type': 'report', 'content': full_response})}\n\n"

            # ── Phase 6: Todo SSE ──
            if tools.get("todo_add") and "[TODO_ADDED]:" in full_response:
                import re as _re6b
                m = _re6b.search(r'\[TODO_ADDED\]:\s*(.+?)\s*\|\s*(.+)', full_response)
                if m:
                    yield f"data: {json.dumps({'type': 'todo_added', 'task': m.group(1), 'time': m.group(2)})}\n\n"

            # ── Phase 6: Note SSE ──
            if tools.get("note_save") and "[NOTE_SAVED]:" in full_response:
                import re as _re6c
                m = _re6c.search(r'\[NOTE_SAVED\]:\s*(.+)', full_response)
                if m:
                    yield f"data: {json.dumps({'type': 'note_saved', 'note': m.group(1)})}\n\n"

            # ── Phase 9: Extract and save facts from user message ──
            if not is_guest:
                facts = extract_facts(data.message)
                if facts:
                    await save_memory(db, user_id, facts)
                    yield f"data: {json.dumps({'type': 'memory_saved', 'facts': list(facts.keys())})}

"
                # Save topic for context
                if tools.get("report") and data.message:
                    import re as _rem
                    topic_str = data.message.lower()
                    for kw in ["generate a report", "make a report", "report on", "report about", "write a report"]:
                        topic_str = topic_str.replace(kw, "").strip()
                    if topic_str:
                        await save_topic(db, user_id, topic_str[:80])

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
