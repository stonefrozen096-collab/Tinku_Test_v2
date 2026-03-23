"""
Tinku Beta Code System
Manages beta access codes for Tinku Lab.
"""
from datetime import datetime
from typing import Optional


# Default beta codes — change these before launch!
DEFAULT_BETA_CODES = {
    "TINKU-BETA-2026":  {"uses": 100, "type": "general"},
    "TINKU-LAB-HARI":   {"uses": 1,   "type": "vip"},
    "TINKU-DEV-001":    {"uses": 10,  "type": "developer"},
}


async def validate_beta_code(db, code: str) -> dict:
    """Validate a beta code and return result."""
    code = code.upper().strip()

    # Check in MongoDB first
    db_code = await db.beta_codes.find_one({"code": code})

    if not db_code:
        # Check default codes
        if code in DEFAULT_BETA_CODES:
            default = DEFAULT_BETA_CODES[code]
            await db.beta_codes.insert_one({
                "code":       code,
                "max_uses":   default["uses"],
                "used":       0,
                "type":       default["type"],
                "created_at": datetime.utcnow(),
                "active":     True
            })
            db_code = await db.beta_codes.find_one({"code": code})
        else:
            return {"valid": False, "message": "Invalid beta code"}

    if not db_code.get("active", True):
        return {"valid": False, "message": "This code has been deactivated"}

    if db_code.get("used", 0) >= db_code.get("max_uses", 1):
        return {"valid": False, "message": "This code has reached its usage limit"}

    return {"valid": True, "type": db_code.get("type", "general")}


async def redeem_beta_code(db, user_id: str, code: str) -> dict:
    """Redeem a beta code for a user."""
    # Check if already beta
    user = await db.users.find_one({"_id": user_id})
    if user and user.get("is_beta"):
        return {"success": False, "message": "You already have beta access!"}

    # Validate code
    result = await validate_beta_code(db, code.upper().strip())
    if not result["valid"]:
        return {"success": False, "message": result["message"]}

    # Grant beta access
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "is_beta":       True,
            "beta_type":     result["type"],
            "beta_since":    datetime.utcnow(),
            "beta_code_used": code.upper().strip()
        }}
    )

    # Increment code usage
    await db.beta_codes.update_one(
        {"code": code.upper().strip()},
        {"$inc": {"used": 1}}
    )

    return {
        "success": True,
        "message": "🎉 Beta access granted! Tinku Lab is now unlocked!",
        "type": result["type"]
    }


async def create_beta_code(db, code: str, max_uses: int = 10,
                           code_type: str = "general") -> dict:
    """Create a new beta code (admin only)."""
    code = code.upper().strip()
    existing = await db.beta_codes.find_one({"code": code})
    if existing:
        return {"success": False, "message": "Code already exists"}

    await db.beta_codes.insert_one({
        "code":       code,
        "max_uses":   max_uses,
        "used":       0,
        "type":       code_type,
        "created_at": datetime.utcnow(),
        "active":     True
    })

    return {"success": True, "message": f"Code {code} created successfully"}
