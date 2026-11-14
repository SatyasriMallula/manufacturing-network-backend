from datetime import date

from django.db import transaction
from rest_framework import serializers
from django.utils import timezone

from organizations.models import Organization
from products.models import Product

from decimal import Decimal
from .models import RFQ, RFQRecipient, RFQAttachment, Quote

class RFQAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = RFQAttachment
        fields = ["id", "file", "title", "created_at"]
        read_only_fields = ["id", "created_at"]


class RFQRecipientSerializer(serializers.ModelSerializer):
    vendor_organization_name = serializers.CharField(source="vendor_organization.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True, default=None)

    class Meta:
        model = RFQRecipient
        fields = ["id", "vendor_organization", "vendor_organization_name", "product", "product_name", "status"]
        read_only_fields = fields


class RFQVendorInputSerializer(serializers.Serializer):
    vendor_organization = serializers.UUIDField()
    product = serializers.UUIDField(required=False, allow_null=True)


class RFQSerializer(serializers.ModelSerializer):
    buyer_organization_name = serializers.CharField(source="buyer_organization.name", read_only=True)
    recipients = serializers.SerializerMethodField()
    attachments = RFQAttachmentSerializer(many=True, read_only=True)
    vendors = RFQVendorInputSerializer(many=True, write_only=True, required=False)

    class Meta:
        model = RFQ
        fields = [
            "id", "rfq_number", "title", "description", "quantity", "unit_of_measurement",
            "required_by_date", "status",
            "buyer_organization", "buyer_organization_name",
            "recipients", "attachments", "vendors",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "rfq_number", "buyer_organization", "created_at", "updated_at"]
        extra_kwargs = {"quantity": {"min_value": 1}}

    def get_recipients(self, obj):
        request = self.context["request"]
        recipients = obj.recipients.select_related("vendor_organization", "product")
        # Vendors only see their own entry, never the other invited vendors.
        if not request.user.is_superuser and request.user.organization_id != obj.buyer_organization_id:
            recipients = recipients.filter(vendor_organization_id=request.user.organization_id)
        return RFQRecipientSerializer(recipients, many=True).data

    def validate_status(self, value):
        if self.instance is None:
            allowed = {RFQ.Status.DRAFT, RFQ.Status.OPEN}
        else:
            allowed = {RFQ.Status.DRAFT, RFQ.Status.OPEN, RFQ.Status.CLOSED, RFQ.Status.CANCELLED}

        if value not in allowed:
            names = ", ".join(s.value for s in allowed)
            raise serializers.ValidationError(f"Allowed values: {names}.")
        return value

    def validate_required_by_date(self, value):
        if value and value < date.today():
            raise serializers.ValidationError("Required-by date cannot be in the past.")
        return value

    def validate_vendors(self, value):
        buyer_org_id = self.context["request"].user.organization_id
        seen = set()
        for item in value:
            vendor_id = item["vendor_organization"]
            if vendor_id == buyer_org_id:
                raise serializers.ValidationError("You cannot send an RFQ to your own organization.")
            if vendor_id in seen:
                raise serializers.ValidationError("The same vendor is listed more than once.")
            seen.add(vendor_id)

            if not Organization.objects.filter( id=vendor_id, is_platform=False, compliance_info__verification_status="verified",
).exists():
                raise serializers.ValidationError(f"Vendor {vendor_id} does not exist or is not verified.")

            product_id = item.get("product")
            if product_id and not Product.objects.filter(
                id=product_id, organization_id=vendor_id, status=Product.Status.ACTIVE
            ).exists():
                raise serializers.ValidationError(
                    f"Product {product_id} is not an active product of vendor {vendor_id}."
                )
        return value

    def validate(self, attrs):
        if self.instance is None:
            status = attrs.get("status", RFQ.Status.OPEN)
            if status == RFQ.Status.OPEN and not attrs.get("vendors"):
                raise serializers.ValidationError({"vendors": "Select at least one vendor to send this RFQ to."})
        return attrs

    def _save_recipients(self, rfq, vendors):
        RFQRecipient.objects.bulk_create([
            RFQRecipient(rfq=rfq, vendor_organization_id=v["vendor_organization"], product_id=v.get("product"))
            for v in vendors
        ])

    def create(self, validated_data):
        vendors = validated_data.pop("vendors", [])
        request = self.context["request"]
        with transaction.atomic():
            rfq = RFQ.objects.create(
                buyer_organization=request.user.organization,
                created_by=request.user,
                **validated_data,
            )
            self._save_recipients(rfq, vendors)
        return rfq

    def update(self, instance, validated_data):
        vendors = validated_data.pop("vendors", None)
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if vendors is not None:
                instance.recipients.all().delete()
                self._save_recipients(instance, vendors)
            if instance.status == RFQ.Status.OPEN and not instance.recipients.exists():
                raise serializers.ValidationError({"vendors": "Select at least one vendor before opening this RFQ."})
        return instance
    
    def validate_quote_deadline(self, value):
        if value and value <= timezone.now():
            raise serializers.ValidationError("Quote deadline must be in the future.")
        return value
    


class QuoteSerializer(serializers.ModelSerializer):
    total_price = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    vendor_organization = serializers.UUIDField(source="recipient.vendor_organization_id", read_only=True)
    vendor_organization_name = serializers.CharField(source="recipient.vendor_organization.name", read_only=True)
    status = serializers.CharField(source="recipient.status", read_only=True)
    class Meta:
        model = Quote
        fields = [
        "id", "vendor_organization", "vendor_organization_name",
        "unit_price", "total_price", "currency", "delivery_days",
        "valid_until", "notes", "status",  "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {
            "unit_price": {"min_value": Decimal("0.01")},
            "delivery_days": {"min_value": 1},
        }

    def validate_valid_until(self, value):
        if value and value < date.today():
            raise serializers.ValidationError("Valid-until date cannot be in the past.")
        return value
    
    def validate_currency(self, value):
        if value != "INR":
            raise serializers.ValidationError("Only INR is supported for now.")
        return value