"""Simple JSON-based order store. Upgrade to SQLite/Postgres later."""
from __future__ import annotations
import json, uuid, threading, hashlib, re
from pathlib import Path
from datetime import datetime

# Centralized data path — honors SIRR_DATA_DIR env var for volume mounts
from paths import ORDERS_DIR
_lock = threading.Lock()


def _make_slug(name: str, dob: str) -> str:
    """Generate a readable URL slug from name + DOB.
    
    'JANE SMITH' + '1990-03-15' → 'jane-smith-15mar1990-a7f3'
    """
    # Take first 3 name parts, lowercase, strip non-alpha
    parts = name.strip().split()[:3]
    slug_parts = [re.sub(r'[^a-z]', '', p.lower()) for p in parts]
    slug_parts = [p for p in slug_parts if p]
    
    # Format DOB as ddMMMyyy
    try:
        dt = datetime.strptime(dob, "%Y-%m-%d")
        dob_str = dt.strftime("%d%b%Y").lower()
    except ValueError:
        dob_str = dob.replace("-", "")
    
    # 4-char hash for uniqueness
    raw = f"{name}:{dob}:{uuid.uuid4().hex[:8]}"
    short_hash = hashlib.sha256(raw.encode()).hexdigest()[:4]
    
    return "-".join(slug_parts + [dob_str, short_hash])

def create_order(data: dict) -> str:
    order_id = _make_slug(data["name_latin"], data["dob"])
    order = {
        "order_id": order_id,
        "status": "pending",          # pending → paid → processing → ready → failed
        "created_at": datetime.utcnow().isoformat(),
        "name_latin": data["name_latin"],
        "name_arabic": data.get("name_arabic", ""),
        "dob": data["dob"],
        "birth_time": data.get("birth_time"),
        "birth_location": data.get("birth_location"),
        "lang": data.get("lang", "en"),
        "stripe_session_id": None,
        "reading_url": None,
        "error": None,
    }
    with _lock:
        (ORDERS_DIR / f"{order_id}.json").write_text(json.dumps(order, indent=2))
    return order_id

def get_order(order_id: str) -> dict | None:
    p = ORDERS_DIR / f"{order_id}.json"
    return json.loads(p.read_text()) if p.exists() else None

def update_order(order_id: str, **kwargs):
    with _lock:
        p = ORDERS_DIR / f"{order_id}.json"
        if not p.exists(): return
        order = json.loads(p.read_text())
        order.update(kwargs)
        p.write_text(json.dumps(order, indent=2))

def get_order_by_stripe_session(session_id: str) -> dict | None:
    for p in ORDERS_DIR.glob("*.json"):
        o = json.loads(p.read_text())
        if o.get("stripe_session_id") == session_id:
            return o
    return None
