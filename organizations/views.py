
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from core.responses import success_response
from .models import Organization
from .serializers import OrganizationSerializer
from core.permissions import IsSuperAdmin


class OrganizationListCreateView(APIView):
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
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request, org_id):
        try:
            organization = Organization.objects.get(id=org_id)
        except Organization.DoesNotExist:
            return success_response(message="Organization not found", data=None, status_code=404)

        return success_response(
            message="Organization fetched",
            data=OrganizationSerializer(organization).data,
        )