from django.utils import timezone

from .models import ComponentDocumentAccess


def _revoke(qs):
    return qs.filter(is_revoked=False).update(is_revoked=True, revoked_at=timezone.now())


def revoke_for_rfq_cancelled(rfq):
    """RFQ cancelled: nobody keeps access."""
    return _revoke(ComponentDocumentAccess.objects.filter(rfq=rfq))


def revoke_for_rfq_awarded(rfq, winner_vendor_org_id):
    """RFQ awarded: vendors who lost no longer share drawings with this buyer."""
    return _revoke(
        ComponentDocumentAccess.objects.filter(rfq=rfq).exclude(
            document__component__organization_id=winner_vendor_org_id
        )
    )


def release_for_order_end(order):
    """Order completed: revoke 'keep until completion' grants. Order cancelled: revoke all."""
    qs = ComponentDocumentAccess.objects.filter(
        rfq=order.rfq, document__component__organization=order.vendor_organization
    )
    if order.status != "completed":
        return _revoke(qs)
    return _revoke(qs.filter(keep_until_completion=True))