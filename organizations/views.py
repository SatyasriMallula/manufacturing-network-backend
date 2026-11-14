from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone

from core.responses import success_response
from core.permissions import IsSuperAdmin, has_role
from .models import Organization, OrganizationComplianceInfo
from .serializers import (
    OrganizationSerializer,
    OrganizationProfileSerializer,
    OrganizationComplianceInfoSerializer,
    OrganizationUpdateSerializer,
)


class OrganizationListCreateView(APIView):
    """Super Admin only: list all orgs, create a new org."""
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        organizations = Organization.objects.all().order_by("-created_at")
        serializer = OrganizationSerializer(organizations, many=True)
        return success_response(message="Organizations fetched", data=serializer.data)

    def post(self, request):
        serializer = OrganizationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = serializer.save()
        return success_response(
            message="Organization created successfully",
            data=OrganizationSerializer(organization).data,
            status_code=201,
        )


class OrganizationDetailView(APIView):
    """Any logged-in user: public profile — name, products, rating.
    This replaces the old separate OrganizationProfileView entirely."""
    permission_classes = [IsAuthenticated]

    def get(self, request, org_id):
        organization = get_object_or_404(Organization, id=org_id)
        serializer = OrganizationProfileSerializer(organization)
        return success_response(message="Organization fetched", data=serializer.data)
    def patch(self, request, org_id):
        organization = get_object_or_404(Organization, id=org_id)
        is_owner = request.user.organization_id == organization.id and has_role(request.user, "company_admin")
        if not (request.user.is_superuser or is_owner):
            return success_response(message="Not allowed", data=None, status_code=403)

        serializer = OrganizationUpdateSerializer(organization, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return success_response(
            message="Organization updated",
            data=OrganizationProfileSerializer(organization).data,
        )


class OrganizationComplianceView(APIView):
    """Owner org or Super Admin only: view/submit sensitive compliance data."""
    permission_classes = [IsAuthenticated]

    def _check_access(self, request, organization):
        return request.user.is_superuser or request.user.organization_id == organization.id

    def get(self, request, org_id):
        organization = get_object_or_404(Organization, id=org_id)
        if not self._check_access(request, organization):
            return success_response(message="Not allowed", data=None, status_code=403)

        compliance = getattr(organization, "compliance_info", None)
        if not compliance:
            return success_response(message="No compliance info submitted yet", data=None)

        return success_response(data=OrganizationComplianceInfoSerializer(compliance).data)

    def put(self, request, org_id):
        organization = get_object_or_404(Organization, id=org_id)
        if not self._check_access(request, organization):
            return success_response(message="Not allowed", data=None, status_code=403)

        compliance, created = OrganizationComplianceInfo.objects.get_or_create(organization=organization)
        serializer = OrganizationComplianceInfoSerializer(compliance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        changed = created or any(
            getattr(compliance, field) != value for field, value in serializer.validated_data.items()
        )
        if changed:
            serializer.save(
                verification_status=OrganizationComplianceInfo.VerificationStatus.PENDING,
                verified_by=None, verified_at=None,
            )
            message = "Compliance info updated, pending verification"
        else:
            message = "No changes detected"
        return success_response(message=message, data=OrganizationComplianceInfoSerializer(compliance).data)


class OrganizationComplianceVerifyView(APIView):
    """Super Admin only: approve or reject a submitted compliance record."""
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def patch(self, request, org_id):
        organization = get_object_or_404(Organization, id=org_id)
        compliance = get_object_or_404(OrganizationComplianceInfo, organization=organization)

        action = request.data.get("action")  # "verify" or "reject"
        required = ["legal_business_name", "gst_number", "pan_number", "bank_account_number"]
        missing = [f for f in required if not getattr(compliance, f)]
        if action == "verify" and missing:
            return success_response(message=f"Cannot verify. Missing: {', '.join(missing)}", data=None, status_code=400)
        if action == "verify":
            compliance.verification_status = OrganizationComplianceInfo.VerificationStatus.VERIFIED
        elif action == "reject":
            compliance.verification_status = OrganizationComplianceInfo.VerificationStatus.REJECTED
        else:
            return success_response(message="Invalid action. Use 'verify' or 'reject'.", data=None, status_code=400)

        compliance.verified_by = request.user
        compliance.verified_at = timezone.now()
        compliance.save()

        return success_response(message=f"Compliance {action}ed", data=OrganizationComplianceInfoSerializer(compliance).data)