"""
Chat Router — Tinku Agent Phase 11
Features: Multi-Agent System (22 Specialized Agents), ReAct Loop, Memory
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
import json
import os

from database import (get_db, save_conversation, save_message,
                      update_user_stats, flag_message)
from providers import check_content, PROVIDERS, generate_response
from routers.auth import get_current_user
from memory import (extract_facts, save_memory, get_memories,
                    save_topic, get_recent_topics, format_memory_context)
from agents.task_manager import TaskManager

router = APIRouter()
task_manager = TaskManager()


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

    # Load memories from DB
    db_memories = {}
    db_topics = []
    if not is_guest:
        db_memories = await get_memories(db, user_id)
        db_topics   = await get_recent_topics(db, user_id, limit=5)

    async def stream():
        full_response = ""

        try:
            # Build context for agents
            db_mem_str = format_memory_context(db_memories, db_topics)
            combined_memory = db_mem_str
            if data.memory_context:
                combined_memory += "\n" + data.memory_context

            # Extract URL from message if present
            import re as _re
            url_match = _re.search(r'https?://[^\s]+', data.message)
            url_value = url_match.group(0) if url_match else ""

            context = {
                "api_key":      data.api_key,
                "provider":     data.provider,
                "model":        data.model,
                "history":      messages[:-1],
                "memory":       combined_memory,
                "user_id":      user_id,
                "conv_id":      conv_id or "",
                "db":           db,
                "file_content": data.file_content,
                "file_name":    data.file_name,
                "image_base64": data.image_base64,
                "image_type":   data.image_type,
                "url_value":    url_value,
            }

            # Run through Task Manager
            async for event in task_manager.process(data.message, context):
                # Capture full response from chunk events
                try:
                    evt = json.loads(event.replace("data: ", "").strip())
                    if evt.get("type") == "chunk":
                        full_response += evt.get("text", "")
                except Exception:
                    pass
                yield event

            # Save memories from this conversation
            if not is_guest:
                facts = extract_facts(data.message)
                if facts:
                    await save_memory(db, user_id, facts)
                    _e = json.dumps({"type": "memory_saved", "facts": list(facts.keys())})
                    yield f"data: {_e}\n\n"

            # Save to DB
            if not is_guest and conv_id and full_response:
                resp_flagged, resp_reason = check_content(full_response)
                await save_message(db, conv_id, user_id, "assistant", full_response,
                                  flagged=resp_flagged, flag_reason=resp_reason)
                await update_user_stats(db, user_id, data.provider, data.model)

        except Exception as e:
            import traceback
            print("STREAM ERROR:", traceback.format_exc())
            _e = json.dumps({"type": "error", "text": str(e)})
            yield f"data: {_e}\n\n"

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


from fastapi import UploadFile, File

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
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
