from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict

from bot.core.types import Intent


def intent_to_dict(intent: Intent) -> Dict[str, Any]:
    payload = asdict(intent)
    payload["timestamp"] = intent.timestamp.isoformat()
    payload["venue"] = intent.venue.value
    payload["order_type_preference"] = intent.order_type_preference.value
    return payload
