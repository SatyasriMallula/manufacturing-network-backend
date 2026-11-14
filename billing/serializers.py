from datetime import date
from decimal import Decimal

from rest_framework import serializers

from .models import Invoice, Payment


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["id", "amount", "method", "reference", "paid_on", "note", "status", "decided_at", "created_at"]
        read_only_fields = ["id", "status", "decided_at", "created_at"]
        extra_kwargs = {"amount": {"min_value": Decimal("0.01")}}

    def validate_paid_on(self, value):
        if value > date.today():
            raise serializers.ValidationError("Payment date cannot be in the future.")
        return value


class InvoiceSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="order.order_number", read_only=True)
    vendor_organization_name = serializers.CharField(source="vendor_organization.name", read_only=True)
    buyer_organization_name = serializers.CharField(source="buyer_organization.name", read_only=True)
    balance = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id", "invoice_number", "order", "order_number",
            "vendor_organization", "vendor_organization_name",
            "buyer_organization", "buyer_organization_name",
            "subtotal", "tax_percent", "tax_amount", "total_amount",
            "paid_amount", "balance", "currency",
            "issue_date", "due_date", "status", "is_overdue", "notes",
            "payments", "created_at", "updated_at","invoice_type", "description"
        ]
        read_only_fields = fields


class InvoiceCreateSerializer(serializers.Serializer):
    order_id = serializers.UUIDField()
    invoice_type = serializers.ChoiceField(choices=Invoice.Type.choices)
    description = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"), required=False)
    percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0.01"), max_value=100, required=False
    )
    tax_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False, default=Decimal("18")
    )
    due_in_days = serializers.IntegerField(min_value=1, max_value=365, required=False, default=30)
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        has_amount, has_percent = "amount" in attrs, "percent" in attrs
        if has_amount and has_percent:
            raise serializers.ValidationError("Send either amount or percent, not both.")
        if not has_amount and not has_percent and attrs["invoice_type"] != Invoice.Type.FINAL:
            raise serializers.ValidationError(
                "Send amount or percent. Only a final invoice can leave both out, because it bills the remaining balance."
            )
        return attrs