from core.permissions import has_role, BUYER_ROLES, VENDOR_ROLES, FINANCE_ROLES
from .models import FileAsset
from django.db.models import Q
C = FileAsset.Category


class EntityPolicy:
    entity_type = ""
    fk_field = ""
    folder = ""
    categories = frozenset()

    def get_parent(self, user, entity_id):
        """The parent record if this user may see it, else None (the API answers 404)."""
        raise NotImplementedError

    def can_modify(self, user, parent):
        """May this user attach or remove files on this parent right now?"""
        raise NotImplementedError

    def can_upload(self, user, parent, category):
        return category in self.categories and self.can_modify(user, parent)

    def can_view(self, user, asset):
        if user.is_superuser or asset.organization_id == user.organization_id:
            return True
        parent = getattr(asset, self.fk_field)
        return self.get_parent(user, parent.pk) is not None

    def can_delete(self, user, asset):
        parent = getattr(asset, self.fk_field)
        return asset.organization_id == user.organization_id and self.can_modify(user, parent)
    
    def visible_assets(self, user, parent, queryset):
        """Which of a parent's files this user may see. Default: all of them."""
        return queryset
    
class ComponentPolicy(EntityPolicy):
    entity_type, fk_field, folder = "component", "component", "components"
    categories = frozenset({C.IMAGE, C.DRAWING, C.SPECIFICATION, C.OTHER})

    def get_parent(self, user, entity_id):
        from components.models import Component
        component = Component.objects.select_related("organization").filter(id=entity_id).first()
        if not component:
            return None
        if user.is_superuser or user.organization_id == component.organization_id:
            return component
        if component.status == Component.Status.ACTIVE and component.organization.is_verified:
            return component
        return None
      
    def can_modify(self, user, parent):
        return user.organization_id == parent.organization_id and has_role(user, "company_admin")

    def _granted_asset_ids(self, user):
        from components.models import ComponentDocumentAccess
        return ComponentDocumentAccess.objects.filter(
            granted_to_organization_id=user.organization_id, is_revoked=False,
            document__file_asset__isnull=False,
        ).exclude(decision="rejected").values_list("document__file_asset_id", flat=True)

    def can_view(self, user, asset):
        if user.is_superuser or asset.organization_id == user.organization_id:
            return True
        component = asset.component
        if asset.category == C.IMAGE:  
            return component.status == "active" and component.organization.is_verified
        from components.models import ComponentDocumentAccess
        return ComponentDocumentAccess.objects.filter(   # drawings and documents: only with an active grant
            granted_to_organization_id=user.organization_id, is_revoked=False,
            document__file_asset_id=asset.id,
        ).exclude(decision="rejected").exists()

    def visible_assets(self, user, parent, queryset):
        if user.is_superuser or user.organization_id == parent.organization_id:
            return queryset
        return queryset.filter(Q(category=C.IMAGE) | Q(id__in=self._granted_asset_ids(user)))

class RFQPolicy(EntityPolicy):
    entity_type, fk_field, folder = "rfq", "rfq", "rfqs"
    categories = frozenset({C.RFQ_ATTACHMENT, C.DRAWING, C.SPECIFICATION, C.OTHER})

    def get_parent(self, user, entity_id):
        from rfqs.views import rfqs_visible_to
        return rfqs_visible_to(user).filter(id=entity_id).first()

    def can_modify(self, user, parent):
        return (
            user.organization_id == parent.buyer_organization_id
            and has_role(user, *BUYER_ROLES)
            and parent.status in ("draft", "open")
        )

    def can_delete(self, user, asset):
        return super().can_delete(user, asset) and asset.rfq.status == "draft"


class QuotePolicy(EntityPolicy):
    entity_type, fk_field, folder = "quote", "quote", "quotes"
    categories = frozenset({C.QUOTATION, C.DRAWING, C.SPECIFICATION, C.OTHER})

    def get_parent(self, user, entity_id):
        from rfqs.models import Quote
        quote = Quote.objects.select_related("recipient__rfq").filter(id=entity_id).first()
        if not quote:
            return None
        rfq = quote.recipient.rfq
        if user.is_superuser or user.organization_id == quote.recipient.vendor_organization_id:
            return quote
        # The buyer sees a quotation file only when the quote itself is visible (sealed-bid rule)
        if user.organization_id == rfq.buyer_organization_id and rfq.quotes_visible_to_buyer():
            return quote
        return None

    def can_modify(self, user, parent):
        from rfqs.models import RFQRecipient
        recipient = parent.recipient
        return (
            user.organization_id == recipient.vendor_organization_id
            and has_role(user, *VENDOR_ROLES)
            and recipient.rfq.accepting_quotes()
            and recipient.status == RFQRecipient.Status.QUOTED
        )


class OrderPolicy(EntityPolicy):
    entity_type, fk_field, folder = "order", "order", "orders"
    categories = frozenset({C.PURCHASE_ORDER, C.DRAWING, C.SPECIFICATION, C.OTHER})

    def get_parent(self, user, entity_id):
        from orders.views import orders_visible_to
        return orders_visible_to(user).filter(id=entity_id).first()

    def can_modify(self, user, parent):
        return (
            user.organization_id in (parent.buyer_organization_id, parent.vendor_organization_id)
            and has_role(user, "company_admin", "sales", "purchase", "production", "quality")
            and parent.status not in ("completed", "cancelled")
        )

    def can_upload(self, user, parent, category):
        if category == C.PURCHASE_ORDER and user.organization_id != parent.buyer_organization_id:
            return False   # only the buyer attaches a purchase order
        return super().can_upload(user, parent, category)


class InvoicePolicy(EntityPolicy):
    entity_type, fk_field, folder = "invoice", "invoice", "invoices"
    categories = frozenset({C.INVOICE, C.OTHER})

    def get_parent(self, user, entity_id):
        from billing.views import invoices_visible_to
        return invoices_visible_to(user).filter(id=entity_id).first()

    def can_modify(self, user, parent):
        return (
            user.organization_id == parent.vendor_organization_id
            and has_role(user, *FINANCE_ROLES)
            and parent.status != "cancelled"
        )

    def can_delete(self, user, asset):
        invoice = asset.invoice
        return (
            super().can_delete(user, asset)
            and invoice.status == "issued"
            and not invoice.payments.exists()
        )


class OrganizationPolicy(EntityPolicy):
    entity_type, fk_field, folder = "organization", "parent_organization", "profile"
    categories = frozenset({C.IMAGE, C.OTHER})

    def get_parent(self, user, entity_id):
        from organizations.models import Organization
        if not (user.is_superuser or user.organization_id == entity_id):
            return None
        return Organization.objects.filter(id=entity_id).first()

    def can_modify(self, user, parent):
        return user.organization_id == parent.id and has_role(user, "company_admin")


REGISTRY = {
    policy.entity_type: policy
    for policy in (
        ComponentPolicy(), RFQPolicy(), QuotePolicy(), OrderPolicy(), InvoicePolicy(), OrganizationPolicy(),
    )
}