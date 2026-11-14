from core.permissions import has_role, BUYER_ROLES
from .models import Order

S = Order.Status

ACTIONS = {
    "confirm": {
        "side": "vendor", "from": {S.PLACED}, "to": S.CONFIRMED,
        "roles": ("company_admin", "sales"),
    },
    "start_production": {
        "side": "vendor", "from": {S.CONFIRMED}, "to": S.IN_PRODUCTION,
        "roles": ("company_admin", "production"),
    },
    "send_to_quality": {
        "side": "vendor", "from": {S.IN_PRODUCTION}, "to": S.QUALITY_CHECK,
        "roles": ("company_admin", "production", "quality"),
    },
    "ship": {
        "side": "vendor", "from": {S.QUALITY_CHECK}, "to": S.SHIPPED,
        "roles": ("company_admin", "sales"),
    },
    "confirm_receipt": {
        "side": "buyer", "from": {S.SHIPPED}, "to": S.COMPLETED,
        "roles": BUYER_ROLES,
    },
    "cancel": {
        "side": "either", "from": {S.PLACED, S.CONFIRMED}, "to": S.CANCELLED,
        "roles": ("company_admin",),
    },
}


def actor_allowed(order, user, rule):
    org_id = user.organization_id
    is_buyer = org_id is not None and org_id == order.buyer_organization_id
    is_vendor = org_id is not None and org_id == order.vendor_organization_id
    side_ok = (
        (rule["side"] == "vendor" and is_vendor)
        or (rule["side"] == "buyer" and is_buyer)
        or (rule["side"] == "either" and (is_buyer or is_vendor))
    )
    return side_ok and has_role(user, *rule["roles"])


def available_actions(order, user):
    """The buttons the frontend should show this user for this order."""
    return [
        name for name, rule in ACTIONS.items()
        if order.status in rule["from"] and actor_allowed(order, user, rule)
    ]