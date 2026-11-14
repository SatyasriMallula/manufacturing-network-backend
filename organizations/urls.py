from django.urls import path
from .views import (
    OrganizationListCreateView,
    OrganizationDetailView,
    OrganizationComplianceView,
    OrganizationComplianceVerifyView,
)

urlpatterns = [
    path("organizations/", OrganizationListCreateView.as_view(), name="organization-list-create"),
    path("organizations/<uuid:org_id>/", OrganizationDetailView.as_view(), name="organization-detail"),
    path("organizations/<uuid:org_id>/compliance/", OrganizationComplianceView.as_view(), name="organization-compliance"),
    path("organizations/<uuid:org_id>/compliance/verify/", OrganizationComplianceVerifyView.as_view(), name="organization-compliance-verify"),
]