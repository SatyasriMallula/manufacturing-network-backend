from django.urls import path
from .views import OrganizationListCreateView, OrganizationDetailView

urlpatterns = [
    path("organizations/", OrganizationListCreateView.as_view(), name="organization-list-create"),
    path("organizations/<uuid:org_id>/", OrganizationDetailView.as_view(), name="organization-detail"),
]