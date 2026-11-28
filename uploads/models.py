import operator
import uuid
from functools import reduce

from django.db import models
from django.db.models import Q

PARENT_FIELDS = ("component", "rfq", "quote", "order", "invoice", "parent_organization")

ENTITY_FK = {
    "component": "component", "rfq": "rfq", "quote": "quote",
    "order": "order", "invoice": "invoice", "organization": "parent_organization",

}
FK_ENTITY = {fk: entity for entity, fk in ENTITY_FK.items()}


def _exactly_one_parent():
    clauses = []
    for name in PARENT_FIELDS:
        clause = Q(**{f"{name}__isnull": False})
        for other in PARENT_FIELDS:
            if other != name:
                clause &= Q(**{f"{other}__isnull": True})
        clauses.append(clause)
    return reduce(operator.or_, clauses)


class FileAssetQuerySet(models.QuerySet):
    def active(self):
        return self.filter(deleted_at__isnull=True)


class FileAsset(models.Model):
    class Category(models.TextChoices):
        IMAGE = "image", "Image"
        DRAWING = "drawing", "Engineering drawing"
        SPECIFICATION = "specification", "Specification"
        RFQ_ATTACHMENT = "rfq_attachment", "RFQ attachment"
        QUOTATION = "quotation", "Quotation"
        PURCHASE_ORDER = "purchase_order", "Purchase order"
        INVOICE = "invoice", "Invoice"
        OTHER = "other", "Other"

    class ScanStatus(models.TextChoices):
        NOT_SCANNED = "not_scanned", "Not scanned"
        CLEAN = "clean", "Clean"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Owner: whose S3 folder it lives in, and who may delete it
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="file_assets")
    uploaded_by = models.ForeignKey("users.User", on_delete=models.SET_NULL, null=True, related_name="uploaded_files")

    object_key = models.CharField(max_length=500, unique=True)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size_bytes = models.BigIntegerField()
    category = models.CharField(max_length=30, choices=Category.choices)
    scan_status = models.CharField(max_length=20, choices=ScanStatus.choices, default=ScanStatus.NOT_SCANNED)

    # Parent: exactly one of these is set (enforced by a database constraint)
    component = models.ForeignKey(
        "components.Component", on_delete=models.CASCADE, null=True, blank=True, related_name="file_assets"
    )
    rfq = models.ForeignKey("rfqs.RFQ", on_delete=models.PROTECT, null=True, blank=True, related_name="file_assets")
    quote = models.ForeignKey("rfqs.Quote", on_delete=models.PROTECT, null=True, blank=True, related_name="file_assets")
    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, null=True, blank=True, related_name="file_assets")
    invoice = models.ForeignKey("billing.Invoice", on_delete=models.PROTECT, null=True, blank=True, related_name="file_assets")
    parent_organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, null=True, blank=True, related_name="profile_file_assets"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)   # soft delete

    objects = FileAssetQuerySet.as_manager()
    s3_deleted_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "-created_at"])]
        constraints = [
            models.CheckConstraint(condition=_exactly_one_parent(), name="fileasset_exactly_one_parent"),
            models.CheckConstraint(condition=Q(size_bytes__gt=0), name="fileasset_size_positive"),
        ]

    @property
    def entity_type(self):
        for fk, entity in FK_ENTITY.items():
            if getattr(self, f"{fk}_id") is not None:
                return entity

    @property
    def entity_id(self):
        for fk in PARENT_FIELDS:
            value = getattr(self, f"{fk}_id")
            if value is not None:
                return value

    def __str__(self):
        return f"{self.original_filename} ({self.category})"