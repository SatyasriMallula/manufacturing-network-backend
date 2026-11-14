import uuid
from decimal import Decimal

from django.db import models
from django.utils import timezone


class Invoice(models.Model):
    class Status(models.TextChoices):
        ISSUED = "issued", "Issued"
        PARTIALLY_PAID = "partially_paid", "Partially paid"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"
        
    class Type(models.TextChoices):
        ADVANCE = "advance", "Advance"
        PROGRESS = "progress", "Progress / milestone"
        FINAL = "final", "Final"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice_number = models.CharField(max_length=30, unique=True, editable=False)

    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="invoices")  # was OneToOne
    invoice_type = models.CharField(max_length=20, choices=Type.choices, default=Type.FINAL)
    description = models.CharField(max_length=200, blank=True)
    vendor_organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="invoices_issued"
    )
    buyer_organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="invoices_received"
    )
    issued_by = models.ForeignKey(
        "users.User", on_delete=models.SET_NULL, null=True, related_name="invoices_issued"
    )

    subtotal = models.DecimalField(max_digits=14, decimal_places=2)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("18.00"))
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="INR")

    issue_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ISSUED)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = f"INV-{timezone.now():%Y%m}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

    @property
    def balance(self):
        return self.total_amount - self.paid_amount

    @property
    def is_overdue(self):
        open_ = self.status in (self.Status.ISSUED, self.Status.PARTIALLY_PAID)
        return open_ and self.due_date < timezone.localdate()

    def __str__(self):
        return self.invoice_number


class Payment(models.Model):
    class Method(models.TextChoices):
        BANK_TRANSFER = "bank_transfer", "Bank transfer"
        CHEQUE = "cheque", "Cheque"
        UPI = "upi", "UPI"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending confirmation"
        CONFIRMED = "confirmed", "Confirmed"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    method = models.CharField(max_length=20, choices=Method.choices)
    reference = models.CharField(max_length=100)          # UTR / cheque number
    paid_on = models.DateField()
    note = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    recorded_by = models.ForeignKey("users.User", on_delete=models.SET_NULL, null=True, related_name="payments_recorded")
    decided_by = models.ForeignKey("users.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="payments_decided")
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.invoice.invoice_number} - {self.amount}"