from core.permissions import BUYER_ROLES, VENDOR_ROLES
from .models import Notification as N
from .services import notify, users_in_org


def rfq_sent(rfq, actor):
    for r in rfq.recipients.all():
        notify(
            users_in_org(r.vendor_organization_id, VENDOR_ROLES),
            N.Type.RFQ_RECEIVED,
            "New request for quote",
            f"{rfq.buyer_organization.name} sent you a request: {rfq.title} (qty {rfq.quantity}).",
            "rfq", rfq.id, actor,
        )


def rfq_closed_or_cancelled(rfq, actor):
    word = "cancelled" if rfq.status == "cancelled" else "closed"
    for r in rfq.recipients.exclude(status="declined"):
        notify(
            users_in_org(r.vendor_organization_id, VENDOR_ROLES),
            N.Type.RFQ_UPDATED,
            f"RFQ {word}",
            f"{rfq.rfq_number} ({rfq.title}) has been {word} by the buyer.",
            "rfq", rfq.id, actor,
        )


def rfq_declined(rfq, recipient, actor):
    notify(
        users_in_org(rfq.buyer_organization_id, BUYER_ROLES),
        N.Type.RFQ_DECLINED,
        "RFQ declined",
        f"{recipient.vendor_organization.name} declined {rfq.rfq_number}.",
        "rfq", rfq.id, actor,
    )


def quote_received(rfq, revised, actor):
    # Deliberately no vendor name or price: keeps sealed bids sealed.
    notify(
        users_in_org(rfq.buyer_organization_id, BUYER_ROLES),
        N.Type.QUOTE_RECEIVED,
        "Quote revised" if revised else "New quote received",
        f"A quote was {'revised' if revised else 'submitted'} on {rfq.rfq_number} ({rfq.title}).",
        "rfq", rfq.id, actor,
    )


def rfq_awarded(rfq, winner, order, actor):
    notify(
        users_in_org(winner.vendor_organization_id, VENDOR_ROLES),
        N.Type.RFQ_AWARDED,
        "You won an RFQ",
        f"{rfq.buyer_organization.name} accepted your quote for {rfq.rfq_number}. "
        f"Order {order.order_number} has been placed.",
        "order", order.id, actor,
    )
    for r in rfq.recipients.filter(status="not_selected"):
        notify(
            users_in_org(r.vendor_organization_id, VENDOR_ROLES),
            N.Type.RFQ_NOT_SELECTED,
            "RFQ not selected",
            f"{rfq.rfq_number} ({rfq.title}) was awarded to another vendor.",
            "rfq", rfq.id, actor,
        )


def order_updated(order, old_status, actor, note=""):
    org_id = actor.organization_id
    if org_id == order.buyer_organization_id:
        targets = [(order.vendor_organization_id, VENDOR_ROLES)]
    elif org_id == order.vendor_organization_id:
        targets = [(order.buyer_organization_id, BUYER_ROLES)]
    else:  # e.g. a superuser acting for the platform
        targets = [
            (order.buyer_organization_id, BUYER_ROLES),
            (order.vendor_organization_id, VENDOR_ROLES),
        ]

    message = f"Order {order.order_number} is now {order.get_status_display()}."
    if note:
        message += f" Note: {note}"

    for target_org_id, roles in targets:
        notify(
            users_in_org(target_org_id, roles),
            N.Type.ORDER_UPDATED, "Order update", message,
            "order", order.id, actor,
        )