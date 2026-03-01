"""
Users Router — profile and usage stats
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from database import get_db
from routers.auth import get_current_user
from bson import ObjectId

router = APIRouter()


@router.get("/me")
async def get_profile(request: Request, db=Depends(get_db)):
    user = get_current_user(request)
    if not user or user.get("is_guest"):
        return {"user": None}

    db_user = await db.users.find_one({"_id": ObjectId(user["user_id"])})
    if not db_user:
        raise HTTPException(status_code=404)

    return {"user": {
        "id": str(db_user["_id"]),
        "name": db_user["name"],
        "email": db_user["email"],
        "photo": db_user.get("photo", ""),
        "provider": db_user.get("provider", "email"),
        "created_at": db_user["created_at"].isoformat(),
    }}


@router.get("/stats")
async def get_stats(request: Request, db=Depends(get_db)):
    user = get_current_user(request)
    if not user or user.get("is_guest"):
        return {"stats": None}

    stats = await db.stats.find_one({"user_id": user["user_id"]})
    if not stats:
        return {"stats": {"total_messages": 0, "messages_by_provider": {}, "messages_by_model": {}}}

    return {"stats": {
        "total_messages": stats.get("total_messages", 0),
        "messages_by_provider": stats.get("messages_by_provider", {}),
        "messages_by_model": stats.get("messages_by_model", {}),
        "last_active": stats.get("last_active", "").isoformat() if stats.get("last_active") else "",
    }}


@router.get("/flagged")
async def get_flagged_messages(request: Request, db=Depends(get_db)):
    """Admin: get all flagged messages."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)

    flagged = await db.messages.find(
        {"user_id": user["user_id"], "flagged": True}
    ).sort("created_at", -1).limit(20).to_list(20)

    return {"flagged": [
        {
            "id": str(m["_id"]),
            "content": m["content"][:100] + "...",
            "flag_reason": m.get("flag_reason", ""),
            "role": m["role"],
            "created_at": m["created_at"].isoformat(),
        }
        for m in flagged
    ]}
