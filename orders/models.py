import uuid
from django.db import models
from django.utils import timezone


class Order(models.Model):
    class Status(models.TextChoices):
        PLACED = "placed", "Placed"
        CONFIRMED = "confirmed", "Confirmed"
        IN_PRODUCTION = "in_production", "In production"
        QUALITY_CHECK = "quality_check", "Quality check"
        SHIPPED = "shipped", "Shipped"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number = models.CharField(max_length=30, unique=True, editable=False)

    rfq = models.OneToOneField("rfqs.RFQ", on_delete=models.PROTECT, related_name="order")
    quote = models.OneToOneField("rfqs.Quote", on_delete=models.PROTECT, related_name="order")
    buyer_organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="purchase_orders"
    )
    vendor_organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="sales_orders"
    )
    component = models.ForeignKey(
        "components.Component", on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )
    created_by = models.ForeignKey("users.User", on_delete=models.SET_NULL, null=True, related_name="orders_created")

    # Snapshot of the agreed deal
    title = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField()
    unit_of_measurement = models.CharField(max_length=50, blank=True)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    total_price = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")
    delivery_days = models.PositiveIntegerField()
    expected_delivery_date = models.DateField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLACED)
    shipping_reference = models.CharField(max_length=100, blank=True)
    cancellation_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = f"ORD-{timezone.now():%Y%m}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order_number} - {self.title}"


class OrderStatusHistory(models.Model):
    """Timeline: who changed the order, when, and why."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="history")
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    changed_by = models.ForeignKey("users.User", on_delete=models.SET_NULL, null=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.order.order_number}: {self.from_status} -> {self.to_status}"
    

from django.core.validators import MaxValueValidator, MinValueValidator

_stars = [MinValueValidator(1), MaxValueValidator(5)]


class OrderReview(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="review")  # one per order
    reviewed_by = models.ForeignKey(
        "users.User", on_delete=models.SET_NULL, null=True, related_name="order_reviews_given"
    )
    rating = models.PositiveSmallIntegerField(validators=_stars)
    quality_rating = models.PositiveSmallIntegerField(null=True, blank=True, validators=_stars)
    accuracy_rating = models.PositiveSmallIntegerField(null=True, blank=True, validators=_stars)
    delivery_rating = models.PositiveSmallIntegerField(null=True, blank=True, validators=_stars)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.order.order_number} - {self.rating}★"