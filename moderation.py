"""
Tinku Auto-Moderation System
Tracks violations, issues warnings, and permanently bans bad actors.
"""
from datetime import datetime, timedelta
from typing import Optional


# ── Violation Levels ──
VIOLATION_WEIGHTS = {
    "prompt_injection":     10,  # Trying to override AI instructions
    "malicious_code":       15,  # Dangerous code execution attempts
    "api_key_theft":        20,  # Trying to steal API keys
    "system_attack":        25,  # Attacking Tinku infrastructure
    "harmful_content":       8,  # Generating harmful content
    "spam":                  3,  # Repeated spam messages
    "sensitive_data":        2,  # Sharing sensitive data (warning only)
}

# Ban thresholds
WARNING_THRESHOLD  = 10   # Show warning
TEMP_BAN_THRESHOLD = 25   # 24 hour ban
PERM_BAN_THRESHOLD = 50   # Permanent ban


async def get_user_violations(db, user_id: str) -> dict:
    """Get violation record for a user."""
    record = await db.moderation.find_one({"user_id": user_id})
    if not record:
        return {
            "user_id":        user_id,
            "violation_score": 0,
            "violations":     [],
            "warnings":       0,
            "is_temp_banned": False,
            "is_perm_banned": False,
            "temp_ban_until": None,
            "banned_at":      None,
            "ban_reason":     None,
        }
    return record


async def add_violation(db, user_id: str, violation_type: str, details: str = "") -> dict:
    """
    Add a violation to user record.
    Returns action taken: "warned", "temp_banned", "perm_banned", or "recorded"
    """
    if user_id == "guest":
        return {"action": "recorded", "score": 0}

    now = datetime.utcnow()
    weight = VIOLATION_WEIGHTS.get(violation_type, 5)

    # Get current record
    record = await get_user_violations(db, user_id)

    # Add violation to history
    violation_entry = {
        "type":      violation_type,
        "details":   details[:200],
        "weight":    weight,
        "timestamp": now
    }

    new_score = record["violation_score"] + weight
    violations = record.get("violations", []) + [violation_entry]

    # Determine action
    action = "recorded"
    is_perm_banned = record.get("is_perm_banned", False)
    is_temp_banned = record.get("is_temp_banned", False)
    temp_ban_until = record.get("temp_ban_until")
    ban_reason = record.get("ban_reason")
    warnings = record.get("warnings", 0)
    banned_at = record.get("banned_at")

    if not is_perm_banned:
        if new_score >= PERM_BAN_THRESHOLD:
            # PERMANENT BAN
            is_perm_banned = True
            is_temp_banned = False
            temp_ban_until = None
            banned_at = now
            ban_reason = f"Permanent ban: Multiple serious violations ({violation_type})"
            action = "perm_banned"

        elif new_score >= TEMP_BAN_THRESHOLD:
            # 24 HOUR TEMP BAN
            is_temp_banned = True
            temp_ban_until = now + timedelta(hours=24)
            ban_reason = f"Temporary ban: Violation threshold exceeded ({violation_type})"
            action = "temp_banned"

        elif new_score >= WARNING_THRESHOLD:
            # WARNING
            warnings += 1
            action = "warned"

    # Update record in MongoDB
    await db.moderation.update_one(
        {"user_id": user_id},
        {"$set": {
            "user_id":         user_id,
            "violation_score": new_score,
            "violations":      violations[-50:],  # Keep last 50
            "warnings":        warnings,
            "is_temp_banned":  is_temp_banned,
            "is_perm_banned":  is_perm_banned,
            "temp_ban_until":  temp_ban_until,
            "banned_at":       banned_at,
            "ban_reason":      ban_reason,
            "updated_at":      now,
        }},
        upsert=True
    )

    return {
        "action":    action,
        "score":     new_score,
        "ban_reason": ban_reason,
    }


async def check_ban_status(db, user_id: str) -> dict:
    """
    Check if user is banned.
    Returns: {"is_banned": bool, "ban_type": str, "message": str}
    """
    if user_id == "guest":
        return {"is_banned": False}

    record = await get_user_violations(db, user_id)

    # Check permanent ban
    if record.get("is_perm_banned"):
        return {
            "is_banned": True,
            "ban_type":  "permanent",
            "message":   "🚫 Your account has been permanently banned from Tinku due to repeated violations of our terms of service. This decision is final."
        }

    # Check temp ban
    if record.get("is_temp_banned"):
        temp_ban_until = record.get("temp_ban_until")
        if temp_ban_until and datetime.utcnow() < temp_ban_until:
            time_left = temp_ban_until - datetime.utcnow()
            hours_left = int(time_left.total_seconds() / 3600)
            mins_left = int((time_left.total_seconds() % 3600) / 60)
            return {
                "is_banned": True,
                "ban_type":  "temporary",
                "message":   f"⏳ Your account is temporarily suspended for {hours_left}h {mins_left}m due to policy violations. Please review Tinku's terms of service."
            }
        else:
            # Temp ban expired — lift it
            await db.moderation.update_one(
                {"user_id": user_id},
                {"$set": {
                    "is_temp_banned": False,
                    "temp_ban_until": None,
                    "ban_reason":     None,
                }}
            )

    return {"is_banned": False}


async def get_warning_message(score: int, warnings: int) -> Optional[str]:
    """Get appropriate warning message based on score."""
    if score >= WARNING_THRESHOLD:
        remaining = PERM_BAN_THRESHOLD - score
        return (
            f"⚠️ Warning #{warnings}: Your account has received a violation. "
            f"Further violations may result in a temporary or permanent ban. "
            f"Please use Tinku responsibly."
        )
    return None


async def get_moderation_stats(db, user_id: str) -> dict:
    """Get moderation stats for admin/user view."""
    record = await get_user_violations(db, user_id)
    return {
        "violation_score": record.get("violation_score", 0),
        "warnings":        record.get("warnings", 0),
        "is_temp_banned":  record.get("is_temp_banned", False),
        "is_perm_banned":  record.get("is_perm_banned", False),
        "ban_reason":      record.get("ban_reason"),
        "total_violations": len(record.get("violations", [])),
    }
