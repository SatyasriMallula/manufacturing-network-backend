# catalog/models.py
import uuid
from django.db import models
from organizations.models import Organization


class Product(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING_REVIEW = "pending_review", "Pending Review"
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="products")

    # Identity
    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=100, blank=True, help_text="Internal part number/SKU")
    category = models.CharField(max_length=100)
    sub_category = models.CharField(max_length=100, blank=True)

    # Description & specs
    description = models.TextField(blank=True)
    materials = models.CharField(max_length=300, blank=True, help_text="e.g. Aluminum 6061, Titanium Ti-6Al-4V")
    manufacturing_processes = models.CharField(max_length=300, blank=True, help_text="e.g. CNC Milling, Investment Casting")
    certifications = models.CharField(max_length=300, blank=True, help_text="e.g. AS9100D, ISO 9001:2015, ITAR Registered")
    tolerance = models.CharField(max_length=100, blank=True)


    # Commercial
    minimum_order_quantity = models.PositiveIntegerField(null=True, blank=True)
    unit_of_measurement = models.CharField(max_length=50, blank=True, help_text="e.g. pcs, kg, meters")
    typical_lead_time_days = models.PositiveIntegerField(null=True, blank=True)

    # Status / moderation
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.organization.name})"


# catalog/models.py
class ProductImage(models.Model):
    class Status(models.TextChoices):
        UPLOADING = "uploading", "Uploading"
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    uploaded_by = models.ForeignKey("users.User", on_delete=models.SET_NULL, null=True)

    original_filename = models.CharField(max_length=255)
    storage_key = models.CharField(max_length=500)          # original, full-size image in S3
    thumbnail_key = models.CharField(max_length=500, blank=True)  # small, for grid views
    medium_key = models.CharField(max_length=500, blank=True)     # medium, for detail page
    image = models.ImageField(upload_to="products/images/",null=True, blank=True)  # the actual image file (used for local storage)


    file_size_bytes = models.BigIntegerField(null=True)
    width = models.PositiveIntegerField(null=True)
    height = models.PositiveIntegerField(null=True)

    is_primary = models.BooleanField(default=False)   # the "main" image shown in listings
    display_order = models.PositiveIntegerField(default=0)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UPLOADING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["display_order", "created_at"]



class ProductDocument(models.Model):
    class DocType(models.TextChoices):
        DRAWING = "drawing", "Engineering Drawing"
        SPEC_SHEET = "spec_sheet", "Spec Sheet"
        CERTIFICATE = "certificate", "Certificate"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        UPLOADING = "uploading", "Uploading"
        SCANNING = "scanning", "Scanning"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"
        REJECTED = "rejected", "Rejected (virus/policy)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="documents")
    uploaded_by = models.ForeignKey("users.User", on_delete=models.SET_NULL, null=True)

    doc_type = models.CharField(max_length=20, choices=DocType.choices)
    original_filename = models.CharField(max_length=255)
    storage_key = models.CharField(max_length=500)   # the S3 path, e.g. "products/{product_id}/docs/{uuid}.pdf"
    file_size_bytes = models.BigIntegerField(null=True)
    content_type = models.CharField(max_length=100, blank=True)
    file = models.FileField(upload_to="products/docs/",null=True, blank=True)  # the actual file (used for local storage)
    title = models.CharField(max_length=200, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UPLOADING)

    created_at = models.DateTimeField(auto_now_add=True)
    

class ProductDocumentAccess(models.Model):
    class Decision(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed by buyer"
        REJECTED = "rejected", "Rejected by buyer"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)  # ← this line was likely missing

    document = models.ForeignKey(ProductDocument, on_delete=models.CASCADE, related_name="access_grants")
    granted_to_organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    granted_by = models.ForeignKey("users.User", on_delete=models.SET_NULL, null=True)
    granted_at = models.DateTimeField(auto_now_add=True)

    decision = models.CharField(max_length=20, choices=Decision.choices, default=Decision.PENDING)
    decided_at = models.DateTimeField(null=True, blank=True)
    rfq = models.ForeignKey(
        "rfqs.RFQ", on_delete=models.SET_NULL, null=True, blank=True, related_name="document_access_grants"
    )
    keep_until_completion = models.BooleanField(default=False)

    is_revoked = models.BooleanField(default=False)
    revoked_at = models.DateTimeField(null=True, blank=True)

    def is_active(self):
        if self.is_revoked:
            return False
        if self.decision == self.Decision.REJECTED:
            return False
        return True