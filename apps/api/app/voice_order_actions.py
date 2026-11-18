"""Safe voice-to-order workflow: draft, read-back, explicit confirmation, commit."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from sqlalchemy import select

from .models_growth import MenuItem, Order, OrderItem, VoiceOrderDraft
from .models_ai import InteractionEvent


def _feature_enabled(db, tenant_id: str) -> bool:
    try:
        from .feature_gate import feature_enabled
        return bool(feature_enabled(db, tenant_id, "online_ordering", True))
    except Exception:
        return False


def _pending(db, tenant, context):
    conversation_id = (context or {}).get("conversation_id")
    if not conversation_id:
        return None
    return db.scalar(
        select(VoiceOrderDraft)
        .where(
            VoiceOrderDraft.tenant_id == tenant.id,
            VoiceOrderDraft.conversation_id == conversation_id,
            VoiceOrderDraft.status == "awaiting_confirmation",
            VoiceOrderDraft.expires_at > datetime.utcnow(),
        )
        .order_by(VoiceOrderDraft.created_at.desc())
    )


def _format_total(value: int) -> str:
    return f"₹{value / 100:.2f}" if value % 100 else f"₹{value // 100}"


async def handle_voice_order(db, tenant, message, language, entities, context):
    """Create a draft from tenant menu data or confirm/cancel the active draft."""
    try:
        if not _feature_enabled(db, tenant.id):
            return "Online ordering is not enabled for this business."
        conversation_id = (context or {}).get("conversation_id")
        if not conversation_id:
            return "I can't safely link this order to the conversation. Please try again."

        draft = _pending(db, tenant, context)
        text = (message or "").strip().lower()

        if draft:
            if re.search(r"\b(no|cancel|don't|do not|stop|नहीं|వద్దు|வேண்டாம்)\b", text):
                draft.status = "cancelled"
                draft.updated_at = datetime.utcnow()
                db.commit()
                return "No problem. I've cancelled that order draft."
            if not re.search(r"\b(yes|confirm|correct|place it|go ahead|అవును|हाँ|சரி)\b", text):
                return "Please say yes to place this order, or no to cancel it."

            # Revalidate every item and its live price immediately before commit.
            items = json.loads(draft.items_json or "[]")
            verified = []
            subtotal = 0
            for entry in items:
                item = db.scalar(select(MenuItem).where(
                    MenuItem.id == entry["menu_item_id"],
                    MenuItem.tenant_id == tenant.id,
                    MenuItem.is_active.is_(True),
                    MenuItem.is_available.is_(True),
                ))
                if not item:
                    draft.status = "stale"
                    db.commit()
                    return f"{entry.get('name', 'An item')} is no longer available. Please place a new order."
                qty = int(entry["quantity"])
                verified.append((item, qty))
                subtotal += int(item.price) * qty

            if subtotal != int(draft.total):
                draft.status = "stale"
                db.commit()
                return "A menu price has changed. I'll prepare a fresh total; please order again."

            customer = None
            customer_obj = (context or {}).get("customer")
            customer_id = getattr(customer_obj, "id", None)
            if customer_id:
                from .models import Customer
                customer = db.scalar(select(Customer).where(
                    Customer.id == customer_id, Customer.tenant_id == tenant.id
                ))

            order = Order(
                tenant_id=tenant.id,
                customer_id=customer.id if customer else None,
                context_token=conversation_id,
                status="pending",
                subtotal=subtotal,
                total=subtotal,
                payment_status="unpaid",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(order)
            db.flush()
            for item, qty in verified:
                db.add(OrderItem(
                    order_id=order.id, menu_item_id=item.id, name=item.name,
                    price=int(item.price), quantity=qty,
                ))
            draft.status = "committed"
            draft.order_id = order.id
            draft.updated_at = datetime.utcnow()
            db.add(InteractionEvent(
                tenant_id=tenant.id,
                customer_id=customer.id if customer else None,
                channel=(context or {}).get("channel", "voice"),
                event_type="voice_order.created",
                payload_json=json.dumps({"order_id": order.id, "total": subtotal}),
            ))
            db.commit()
            try:
                from .events import publish_event_sync
                publish_event_sync(tenant.id, "order.created", {
                    "order_id": order.id, "status": order.status,
                    "total": order.total, "customer_id": order.customer_id,
                    "source": "voice",
                }, context_token=conversation_id)
            except Exception:
                # The order is durable; event delivery must be retried independently.
                pass
            return f"Confirmed. Your order number is {order.id[:8]}. The total is {_format_total(subtotal)}. Payment is still pending."
        
        if re.search(r"\b(order|place|want|add|buy|send me|give me)\b", text) is None:
            return None

        menu = db.scalars(select(MenuItem).where(
            MenuItem.tenant_id == tenant.id,
            MenuItem.is_active.is_(True),
            MenuItem.is_available.is_(True),
        ).order_by(MenuItem.sort_order)).all()
        if not menu:
            return "The menu is not available right now. I can ask the team to help."

        # Match exact menu names only; never infer a product from a vague phrase.
        matched = []
        for item in menu:
            name = (item.name or "").strip().lower()
            if name and re.search(r"(?<![\w])" + re.escape(name) + r"(?![\w])", text):
                qty_match = re.search(r"\b(\d{1,2})\s*(?:x\s*)?" + re.escape(name) + r"\b", text)
                if not qty_match:
                    qty_match = re.search(r"\b" + re.escape(name) + r"\s*(?:x\s*)?(\d{1,2})\b", text)
                qty = int(qty_match.group(1)) if qty_match else 1
                if qty < 1 or qty > 50:
                    return f"How many {item.name} would you like? Please say a quantity from 1 to 50."
                matched.append({"menu_item_id": item.id, "name": item.name, "price": int(item.price), "quantity": qty})

        if len(matched) == 0:
            return "I couldn't match that to an available menu item. Please tell me the exact item name from the menu."
        if len(matched) > 12:
            return "Let's add up to 12 menu items at a time. Please split the order."

        subtotal = sum(x["price"] * x["quantity"] for x in matched)
        draft = VoiceOrderDraft(
            tenant_id=tenant.id,
            conversation_id=conversation_id,
            customer_id=getattr((context or {}).get("customer"), "id", None),
            items_json=json.dumps(matched),
            total=subtotal,
            status="awaiting_confirmation",
            expires_at=datetime.utcnow() + timedelta(minutes=15),
        )
        db.add(draft)
        db.commit()
        readback = ", ".join(f'{x["quantity"]} {x["name"]} at {_format_total(x["price"])} each' for x in matched)
        return f"Please confirm: {readback}. The total is {_format_total(subtotal)}. Shall I place this order?"
    except Exception:
        db.rollback()
        return "I couldn't safely complete that order. Nothing has been placed. Please try again or ask the team for help."
