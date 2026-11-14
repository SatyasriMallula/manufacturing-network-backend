import uuid
from django.db import models


class Notification(models.Model):
    class Type(models.TextChoices):
        RFQ_RECEIVED = "rfq_received", "RFQ received"
        RFQ_UPDATED = "rfq_updated", "RFQ updated"
        RFQ_DECLINED = "rfq_declined", "RFQ declined"
        QUOTE_RECEIVED = "quote_received", "Quote received"
        RFQ_AWARDED = "rfq_awarded", "RFQ awarded"
        RFQ_NOT_SELECTED = "rfq_not_selected", "RFQ not selected"
        ORDER_UPDATED = "order_updated", "Order updated"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="notifications")
    notification_type = models.CharField(max_length=30, choices=Type.choices)
    title = models.CharField(max_length=200)
    message = models.TextField()

    # What it points to, so the frontend can open the right screen
    target_type = models.CharField(max_length=20)   # "rfq" or "order"
    target_id = models.UUIDField()

    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "is_read", "-created_at"])]

    def __str__(self):
        return f"{self.recipient} - {self.title}"