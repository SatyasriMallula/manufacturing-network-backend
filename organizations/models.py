import uuid
from django.db import models


class Organization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    is_platform = models.BooleanField(default=False)  # True only for your own company
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    description = models.TextField(blank=True)
    website = models.URLField(blank=True)
    year_established = models.PositiveIntegerField(null=True, blank=True)
    address_city = models.CharField(max_length=100, blank=True)
    address_state = models.CharField(max_length=100, blank=True)
    address_country = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.name
    
    @property
    def is_verified(self):
        info = getattr(self, "compliance_info", None)
        return bool(info and info.verification_status == "verified")

class OrganizationComplianceInfo(models.Model):
    class VerificationStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"

    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name="compliance_info")
    legal_business_name = models.CharField(max_length=200, blank=True)
    gst_number = models.CharField(max_length=20, blank=True)
    pan_number = models.CharField(max_length=20, blank=True)
    bank_account_number = models.CharField(max_length=50, blank=True)
    bank_ifsc_code = models.CharField(max_length=20, blank=True)
    certifications = models.CharField(max_length=500, blank=True)

    verification_status = models.CharField(max_length=20, choices=VerificationStatus.choices, default=VerificationStatus.PENDING)
    verified_by = models.ForeignKey("users.User", on_delete=models.SET_NULL, null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Compliance info for {self.organization.name}"