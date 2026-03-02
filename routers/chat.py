"""
Chat Router — Tinku Agent v3
NEW: Tool routing, thinking steps, web search, live weather
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
import json
from datetime import datetime

from database import (get_db, save_conversation, save_message,
                      update_user_stats, flag_message)
from providers import (generate_response, check_content, PROVIDERS,
                       detect_tools_needed, get_weather, web_search,
                       get_exchange_rate)
from routers.auth import get_current_user

router = APIRouter()


class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    history: List[Message] = []
    provider: str = "gemini"
    model: str = "gemini-2.0-flash"
    api_key: str
    conversation_id: Optional[str] = None


def make_step(emoji: str, text: str) -> str:
    """Create a thinking step SSE event."""
    return f"data: {json.dumps({'type': 'step', 'emoji': emoji, 'text': text})}\n\n"


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
        tool_context = ""

        try:
            # ── STEP 1: Analyze ──
            yield make_step("🤔", "Analyzing your question...")

            # Detect tools needed
            tools = detect_tools_needed(data.message)
            needs_tools = tools["weather"] or tools["search"] or tools["currency"]

            if needs_tools:
                yield make_step("⚙️", "Deciding which tools to use...")

            # ── STEP 2: Run Tools ──
            if tools["weather"]:
                city = tools["city"] or "Mumbai"
                yield make_step("🌤", f"Fetching live weather for {city}...")
                weather_data = await get_weather(city)
                tool_context += f"\n\n[LIVE WEATHER DATA]\n{weather_data}\n"

            if tools["search"]:
                yield make_step("🔍", f"Searching the web...")
                search_data = await web_search(data.message)
                tool_context += f"\n\n[WEB SEARCH RESULTS]\n{search_data}\n"

            if tools["currency"]:
                yield make_step("💱", "Fetching live exchange rates...")
                currency_data = await get_exchange_rate()
                tool_context += f"\n\n[LIVE EXCHANGE RATES]\n{currency_data}\n"

            # ── STEP 3: Think ──
            yield make_step("💡", "Preparing your answer...")

            # If flagged, warn
            if is_flagged:
                warning = "⚠️ Your message was flagged for review. I'll still try to help responsibly.\n\n"
                yield f"data: {json.dumps({'type': 'chunk', 'text': warning})}\n\n"
                full_response += warning

            # Inject tool results into message if we have them
            final_messages = messages.copy()
            if tool_context:
                # Append tool data to last user message
                final_messages[-1] = {
                    "role": "user",
                    "content": data.message + tool_context +
                               "\n\n[Use the above real-time data to answer the user's question accurately and helpfully.]"
                }

            # ── STEP 4: Generate AI Response ──
            yield make_step("✨", "Generating response...")

            async for chunk in generate_response(final_messages, data.provider, data.model, data.api_key):
                full_response += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"

            # Save response
            if not is_guest and conv_id:
                resp_flagged, resp_reason = check_content(full_response)
                await save_message(db, conv_id, user_id, "assistant", full_response,
                                  flagged=resp_flagged, flag_reason=resp_reason)
                await update_user_stats(db, user_id, data.provider, data.model)

            yield f"data: {json.dumps({'type': 'done', 'conversation_id': conv_id or ''})}\n\n"

        except Exception as e:
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
