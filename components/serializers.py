from rest_framework import serializers
from django.db.models import Avg, Count
from .models import Component, ComponentDocument
from orders.models import OrderReview


def _review_stats(component):
    if not hasattr(component, "_review_stats"):
        component._review_stats = OrderReview.objects.filter(order__component=component).aggregate(
            avg=Avg("rating"), n=Count("id")
        )
    return component._review_stats


class ComponentSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    average_rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()

    class Meta:
        model = Component
        fields = [
            "id", "organization", "organization_name", "name", "sku", "category",
            "sub_category", "description", "materials", "manufacturing_processes",
            "certifications", "tolerance", "minimum_order_quantity",
            "unit_of_measurement", "typical_lead_time_days", "status",
            "average_rating", "review_count", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "organization", "created_at", "updated_at"]  
        
    def validate_status(self, value):
        allowed = [Component.Status.ACTIVE, Component.Status.INACTIVE, Component.Status.DRAFT]
        if value not in allowed:
            raise serializers.ValidationError(
                f"You can only set status to one of: {', '.join(allowed)}"
            )
        return value

    def get_average_rating(self, obj):
        if hasattr(obj, "avg_rating"):  # pre-calculated by the list view
            return round(obj.avg_rating, 1) if obj.avg_rating else None
        avg = _review_stats(obj)["avg"]
        return round(avg, 1) if avg else None

    def get_review_count(self, obj):
        if hasattr(obj, "num_reviews"):
            return obj.num_reviews
        return _review_stats(obj)["n"]


class SubmitComponentReviewSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    quality_rating = serializers.IntegerField(min_value=1, max_value=5, required=False)
    accuracy_rating = serializers.IntegerField(min_value=1, max_value=5, required=False)
    delivery_rating = serializers.IntegerField(min_value=1, max_value=5, required=False)
    comment = serializers.CharField(required=False, allow_blank=True)

class AttachImageSerializer(serializers.Serializer):
    file_asset_id = serializers.UUIDField()
    is_primary = serializers.BooleanField(required=False, default=False)
    display_order = serializers.IntegerField(required=False, min_value=0, default=0)


class AttachDocumentSerializer(serializers.Serializer):
    file_asset_id = serializers.UUIDField()
    doc_type = serializers.ChoiceField(choices=ComponentDocument.DocType.choices)
    title = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")