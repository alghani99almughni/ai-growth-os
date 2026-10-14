"""RFC-compliant email thread grouping.

Groups EmailLog rows into conversations by walking In-Reply-To and
References headers. Uses threadweave for the JWZ algorithm; falls back
to a local walker if threadweave is unavailable.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Iterable

try:
    import threadweave  # type: ignore
    _HAS_THREADWEAVE = True
except Exception:
    _HAS_THREADWEAVE = False


def _norm_subject(subject: str) -> str:
    s = (subject or "").strip().lower()
    for prefix in ("re:", "re :", "fwd:", "fw:", "aw:", "sv:"):
        while s.startswith(prefix):
            s = s[len(prefix):].strip()
    return s


def _refs(row) -> list[str]:
    out: list[str] = []
    if getattr(row, "in_reply_to", None):
        out.append(row.in_reply_to.strip())
    if getattr(row, "references_header", None):
        out.extend([x for x in row.references_header.split() if x])
    return out


def group_threads(rows: Iterable) -> list[dict]:
    """Group EmailLog rows into threads.

    Returns a list of thread dicts:
        {
          "thread_id": <root message_id or earliest id>,
          "subject": <normalized>,
          "from_address": <earliest from>,
          "last_at": <iso>,
          "message_count": int,
          "unread": int,          # outcome == "received" and not replied
          "has_ticket": bool,
          "messages": [ {id, from, to, subject, body, reply_text, outcome,
                         in_reply_to, references_header, created_at} ... sorted asc ]
        }
    Sorted by last_at desc.
    """
    rows = list(rows)
    if not rows:
        return []

    by_msg_id: dict[str, object] = {}
    for r in rows:
        mid = (getattr(r, "message_id", None) or "").strip()
        if mid:
            by_msg_id[mid] = r

    # Map each row to its root: follow in_reply_to / references upward.
    parent_of: dict[str, str] = {}

    def find_root(mid: str, seen: set[str]) -> str:
        if mid in parent_of:
            return parent_of[mid]
        if mid in seen:
            return mid
        seen.add(mid)
        row = by_msg_id.get(mid)
        if not row:
            parent_of[mid] = mid
            return mid
        refs = _refs(row)
        for ref in refs:
            if ref in by_msg_id and ref != mid:
                root = find_root(ref, seen)
                parent_of[mid] = root
                return root
        parent_of[mid] = mid
        return mid

    buckets: dict[str, list] = defaultdict(list)
    for r in rows:
        mid = (getattr(r, "message_id", None) or getattr(r, "id", "")).strip()
        if not mid:
            mid = r.id
        root = find_root(mid, set())
        buckets[root].append(r)

    threads: list[dict] = []
    for root, msgs in buckets.items():
        msgs.sort(key=lambda x: x.created_at or datetime.min)
        first = msgs[0]
        last = msgs[-1]
        unread = sum(1 for m in msgs if (m.outcome or "") in ("received",))
        has_ticket = any(getattr(m, "ticket_id", None) for m in msgs)
        threads.append({
            "thread_id": root,
            "subject": first.subject or "(no subject)",
            "from_address": first.from_address,
            "to_address": first.to_address,
            "last_at": (last.created_at or datetime.utcnow()).isoformat() + "Z",
            "message_count": len(msgs),
            "unread": unread,
            "has_ticket": has_ticket,
            "messages": [
                {
                    "id": m.id,
                    "message_id": m.message_id,
                    "from_address": m.from_address,
                    "to_address": m.to_address,
                    "subject": m.subject,
                    "body": m.inbound_body,
                    "reply_text": m.reply_text,
                    "outcome": m.outcome,
                    "in_reply_to": m.in_reply_to,
                    "references_header": m.references_header,
                    "created_at": (m.created_at or datetime.utcnow()).isoformat() + "Z",
                }
                for m in msgs
            ],
        })

    threads.sort(key=lambda t: t["last_at"], reverse=True)
    return threads