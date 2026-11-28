import uuid
from django.db import models
from django.utils import timezone


def rfq_attachment_path(instance, filename):
    return f"rfqs/{instance.rfq.id}/attachments/{uuid.uuid4()}_{filename}"


class RFQ(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"
        AWARDED = "awarded", "Awarded"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rfq_number = models.CharField(max_length=30, unique=True, editable=False)

    buyer_organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="rfqs_raised"
    )
    created_by = models.ForeignKey(
        "users.User", on_delete=models.SET_NULL, null=True, related_name="rfqs_created"
    )

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    quantity = models.PositiveIntegerField()
    unit_of_measurement = models.CharField(max_length=50, blank=True)
    required_by_date = models.DateField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    awarded_recipient = models.OneToOneField(
            "RFQRecipient", null=True, blank=True,
            on_delete=models.SET_NULL, related_name="awarded_rfq",
        )
    awarded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    quote_deadline = models.DateTimeField(null=True, blank=True)
    sealed_bids = models.BooleanField(default=False)

    def accepting_quotes(self):
        """Vendors can submit or revise quotes."""
        if self.status != self.Status.OPEN:
            return False
        return not self.quote_deadline or timezone.now() < self.quote_deadline

    def quotes_visible_to_buyer(self):
        if self.status in (self.Status.CLOSED, self.Status.AWARDED):
            return True
        if self.status != self.Status.OPEN:
            return False
        if not self.sealed_bids:
            return True
        return bool(self.quote_deadline and timezone.now() >= self.quote_deadline)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.rfq_number:
            self.rfq_number = f"RFQ-{timezone.now():%Y%m}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.rfq_number} - {self.title}"


class RFQRecipient(models.Model):
    """One row per vendor the RFQ was sent to."""
    class Status(models.TextChoices):
        SENT = "sent", "Sent"
        VIEWED = "viewed", "Viewed"
        QUOTED = "quoted", "Quoted"
        DECLINED = "declined", "Declined"
        AWARDED = "awarded", "Awarded"
        NOT_SELECTED = "not_selected", "Not selected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rfq = models.ForeignKey(RFQ, on_delete=models.CASCADE, related_name="recipients")
    vendor_organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="rfqs_received"
    )
    component = models.ForeignKey(
        "components.Component", on_delete=models.SET_NULL, null=True, blank=True, related_name="rfq_recipients"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SENT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("rfq", "vendor_organization")

    def __str__(self):
        return f"{self.rfq.rfq_number} -> {self.vendor_organization.name}"
    
class Quote(models.Model):
   
    """A vendor's price offer for one RFQ."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.OneToOneField(RFQRecipient, on_delete=models.CASCADE, related_name="quote")

    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")
    delivery_days = models.PositiveIntegerField()
    valid_until = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_by = models.ForeignKey(
        "users.User", on_delete=models.SET_NULL, null=True, related_name="quotes_submitted"
    )

    @property
    def total_price(self):
        return self.unit_price * self.recipient.rfq.quantity

    def __str__(self):
        return f"{self.recipient.rfq.rfq_number} - {self.recipient.vendor_organization.name}"

class RFQAttachment(models.Model):
    """The buyer's own designs/drawings for this request."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rfq = models.ForeignKey(RFQ, on_delete=models.CASCADE, related_name="attachments")
    uploaded_by = models.ForeignKey("users.User", on_delete=models.SET_NULL, null=True)
    file_asset = models.OneToOneField(
        "uploads.FileAsset", on_delete=models.SET_NULL, null=True, blank=True, related_name="rfq_attachment"
    )
    title = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title or 'Attachment'} - {self.rfq.rfq_number}"