from rest_framework import serializers

from .models import Order, OrderStatusHistory
from .workflow import available_actions
from core.permissions import has_role, BUYER_ROLES
from .models import Order, OrderStatusHistory, OrderReview
from decimal import Decimal
from django.db.models import Sum

class OrderHistorySerializer(serializers.ModelSerializer):
    changed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = OrderStatusHistory
        fields = ["from_status", "to_status", "changed_by_name", "note", "created_at"]

    def get_changed_by_name(self, obj):
        if not obj.changed_by:
            return None
        name = f"{obj.changed_by.first_name} {obj.changed_by.last_name}".strip()
        return name or obj.changed_by.email


class OrderSerializer(serializers.ModelSerializer):
    rfq_number = serializers.CharField(source="rfq.rfq_number", read_only=True)
    buyer_organization_name = serializers.CharField(source="buyer_organization.name", read_only=True)
    vendor_organization_name = serializers.CharField(source="vendor_organization.name", read_only=True)
    component_name = serializers.CharField(source="component.name", read_only=True, default=None)
    available_actions = serializers.SerializerMethodField()
    can_review = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id", "order_number", "rfq", "rfq_number", "title",
            "buyer_organization", "buyer_organization_name",
            "vendor_organization", "vendor_organization_name",
            "component", "component_name",
            "quantity", "unit_of_measurement", "unit_price", "total_price", "currency",
            "delivery_days", "expected_delivery_date",
            "status", "shipping_reference", "cancellation_reason",
            "available_actions", "created_at", "updated_at","can_review"
        ]
        read_only_fields = fields

    def get_available_actions(self, obj):
        return available_actions(obj, self.context["request"].user)
    
    def get_can_review(self, obj):
        user = self.context["request"].user
        return (
            obj.status == Order.Status.COMPLETED
            and user.organization_id == obj.buyer_organization_id
            and has_role(user, *BUYER_ROLES)
            and not hasattr(obj, "review")
        )



class OrderDetailSerializer(OrderSerializer):
    history = OrderHistorySerializer(many=True, read_only=True)
    invoiced_amount = serializers.SerializerMethodField()
    remaining_to_invoice = serializers.SerializerMethodField()

    class Meta(OrderSerializer.Meta):
        fields = OrderSerializer.Meta.fields + ["history", "invoiced_amount", "remaining_to_invoice"]
        read_only_fields = fields

    def _invoiced(self, obj):
        if not hasattr(obj, "_invoiced"):
            obj._invoiced = obj.invoices.exclude(status="cancelled").aggregate(
                s=Sum("subtotal")
            )["s"] or Decimal("0.00")
        return obj._invoiced

    def get_invoiced_amount(self, obj):
        return self._invoiced(obj)

    def get_remaining_to_invoice(self, obj):
        return obj.total_price - self._invoiced(obj)




class OrderReviewSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="order.order_number", read_only=True)
    buyer_organization_name = serializers.CharField(source="order.buyer_organization.name", read_only=True)
    reviewed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = OrderReview
        fields = [
            "id", "order_number", "buyer_organization_name", "reviewed_by_name",
            "rating", "quality_rating", "accuracy_rating", "delivery_rating",
            "comment", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_reviewed_by_name(self, obj):
        if not obj.reviewed_by:
            return None
        name = f"{obj.reviewed_by.first_name} {obj.reviewed_by.last_name}".strip()
        return name or obj.reviewed_by.email