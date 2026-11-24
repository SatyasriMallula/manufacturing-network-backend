from django.db.models import Avg
from rest_framework import serializers

from .models import Organization, OrganizationComplianceInfo


class OrganizationSerializer(serializers.ModelSerializer):
    """Used by Super Admin for list/create."""
    class Meta:
        model = Organization
        fields = ["id", "name", "is_platform", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

from datetime import date

from django.db.models import Avg, Count
from rest_framework import serializers

from orders.models import OrderReview
from components.models import Component


class OrganizationProfileSerializer(serializers.ModelSerializer):
    is_verified = serializers.BooleanField(read_only=True)
    overall_rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()
    component_count = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            "id", "name", "description", "website", "year_established",
            "address_city", "address_state", "address_country", "created_at",
            "is_verified", "overall_rating", "review_count", "component_count",
        ]

    def _stats(self, obj):
        if not hasattr(obj, "_review_stats"):
            obj._review_stats = OrderReview.objects.filter(
                order__vendor_organization=obj
            ).aggregate(avg=Avg("rating"), n=Count("id"))
        return obj._review_stats

    def get_overall_rating(self, obj):
        avg = self._stats(obj)["avg"]
        return round(avg, 1) if avg else None

    def get_review_count(self, obj):
        return self._stats(obj)["n"]

    def get_component_count(self, obj):
        return Component.objects.filter(organization=obj, status=Component.Status.ACTIVE).count()


class OrganizationUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = [
            "description", "website", "year_established",
            "address_city", "address_state", "address_country",
        ]

    def validate_year_established(self, value):
        if value is not None and not (1800 <= value <= date.today().year):
            raise serializers.ValidationError("Enter a valid year.")
        return value

class OrganizationComplianceInfoSerializer(serializers.ModelSerializer):
    """Sensitive data. Only ever returned by OrganizationComplianceView,
    never by OrganizationSerializer or OrganizationProfileSerializer."""
    class Meta:
        model = OrganizationComplianceInfo
        fields = [
            "legal_business_name", "gst_number", "pan_number",
            "bank_account_number", "bank_ifsc_code", "certifications",
            "verification_status", "verified_at",
        ]
        read_only_fields = ["verification_status", "verified_at"]