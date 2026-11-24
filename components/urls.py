from django.urls import path
from .views import (
    MyComponentListCreateView, MyComponentDetailView,
    ComponentImageListCreateView, ComponentImageDeleteView,
    ComponentDocumentListCreateView, ComponentDocumentDeleteView,
    ComponentReviewListView, PublicComponentListView,
)

from .views import DocumentAccessListGrantView, DocumentAccessActionView

urlpatterns = [
    path("components/", PublicComponentListView.as_view(), name="component-list"),

    path("components/my/", MyComponentListCreateView.as_view(), name="my-components"),
    path("components/my/<uuid:component_id>/", MyComponentDetailView.as_view(), name="my-component-detail"),

    path("components/<uuid:component_id>/images/", ComponentImageListCreateView.as_view(), name="component-images"),
    path("components/<uuid:component_id>/images/<uuid:image_id>/", ComponentImageDeleteView.as_view(), name="component-image-delete"),

    path("components/<uuid:component_id>/documents/", ComponentDocumentListCreateView.as_view(), name="component-documents"),
    path("components/<uuid:component_id>/documents/<uuid:document_id>/", ComponentDocumentDeleteView.as_view(), name="component-document-delete"),

    path("components/<uuid:component_id>/reviews/", ComponentReviewListView.as_view(), name="component-reviews"),
    
    path("documents/<uuid:document_id>/access/", DocumentAccessListGrantView.as_view(), name="document-access"),
    path("documents/<uuid:document_id>/access/action/", DocumentAccessActionView.as_view(), name="document-access-action"),
]