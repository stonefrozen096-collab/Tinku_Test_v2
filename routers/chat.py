"""
Chat Router — handles all conversation logic
- Send messages
- Stream responses
- Save to MongoDB
- Flag inappropriate content
- Get conversation history
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
import json
from datetime import datetime

from database import (get_db, save_conversation, save_message,
                      update_user_stats, flag_message)
from providers import generate_response, check_content, PROVIDERS
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


@router.post("/send")
async def send_message(data: ChatRequest, request: Request, db=Depends(get_db)):
    """Send a message and stream the response."""
    user = get_current_user(request)
    user_id = user["user_id"] if user else "guest"
    is_guest = not user or user.get("is_guest", False)

    # Content moderation on user message
    is_flagged, flag_reason = check_content(data.message)

    # Build message history
    messages = [{"role": m.role, "content": m.content} for m in data.history]
    messages.append({"role": "user", "content": data.message})

    # Save conversation if not guest
    conv_id = data.conversation_id
    if not is_guest and not conv_id:
        title = data.message[:50] + ("..." if len(data.message) > 50 else "")
        conv_id = await save_conversation(db, user_id, title, data.model, data.provider)

    # Save user message
    user_msg_id = None
    if not is_guest:
        user_msg_id = await save_message(
            db, conv_id, user_id, "user", data.message,
            flagged=is_flagged, flag_reason=flag_reason
        )

    async def stream():
        full_response = ""
        try:
            # If flagged, still respond but note it
            if is_flagged:
                warning = "⚠️ Your message was flagged for review. I'll still try to help responsibly.\n\n"
                yield f"data: {json.dumps({'type': 'chunk', 'text': warning})}\n\n"
                full_response += warning

            # Stream from AI provider
            async for chunk in generate_response(messages, data.provider, data.model, data.api_key):
                full_response += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"

            # Save assistant response
            if not is_guest and conv_id:
                resp_flagged, resp_flag_reason = check_content(full_response)
                await save_message(
                    db, conv_id, user_id, "assistant", full_response,
                    flagged=resp_flagged, flag_reason=resp_flag_reason
                )
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
    """Get all conversations for the current user."""
    user = get_current_user(request)
    if not user or user.get("is_guest"):
        return {"conversations": []}

    convos = await db.conversations.find(
        {"user_id": user["user_id"]}
    ).sort("updated_at", -1).limit(50).to_list(50)

    return {"conversations": [
        {
            "id": str(c["_id"]),
            "title": c["title"],
            "model": c.get("model", ""),
            "provider": c.get("provider", ""),
            "message_count": c.get("message_count", 0),
            "updated_at": c["updated_at"].isoformat(),
        }
        for c in convos
    ]}


@router.get("/conversations/{conv_id}/messages")
async def get_messages(conv_id: str, request: Request, db=Depends(get_db)):
    """Get all messages in a conversation."""
    user = get_current_user(request)
    if not user or user.get("is_guest"):
        raise HTTPException(status_code=401, detail="Login required")

    from bson import ObjectId
    conv = await db.conversations.find_one({
        "_id": ObjectId(conv_id),
        "user_id": user["user_id"]
    })
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msgs = await db.messages.find(
        {"conversation_id": conv_id}
    ).sort("created_at", 1).to_list(500)

    return {"messages": [
        {
            "id": str(m["_id"]),
            "role": m["role"],
            "content": m["content"],
            "created_at": m["created_at"].isoformat(),
            "flagged": m.get("flagged", False),
        }
        for m in msgs
    ]}


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str, request: Request, db=Depends(get_db)):
    """Delete a conversation."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)

    from bson import ObjectId
    await db.conversations.delete_one({"_id": ObjectId(conv_id), "user_id": user["user_id"]})
    await db.messages.delete_many({"conversation_id": conv_id})
    return {"success": True}


@router.get("/providers")
async def get_providers():
    """Return available AI providers and their models."""
    return {"providers": PROVIDERS}
