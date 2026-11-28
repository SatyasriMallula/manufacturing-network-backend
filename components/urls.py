from django.urls import path
from .views import (
    ComponentDocumentDetailView, MyComponentListCreateView, MyComponentDetailView,
    ComponentImageListCreateView, ComponentImageDetailView,
    ComponentDocumentListCreateView, 
    ComponentReviewListView, PublicComponentListView,
)

from .views import DocumentAccessListGrantView, DocumentAccessActionView

urlpatterns = [
    path("components/", PublicComponentListView.as_view(), name="component-list"),

    path("components/my/", MyComponentListCreateView.as_view(), name="my-components"),
    path("components/my/<uuid:component_id>/", MyComponentDetailView.as_view(), name="my-component-detail"),

    path("components/<uuid:component_id>/images/", ComponentImageListCreateView.as_view()),
    path("components/<uuid:component_id>/images/<uuid:image_id>/", ComponentImageDetailView.as_view()),
    path("components/<uuid:component_id>/documents/", ComponentDocumentListCreateView.as_view()),
    path("components/<uuid:component_id>/documents/<uuid:document_id>/", ComponentDocumentDetailView.as_view()),

    path("components/<uuid:component_id>/reviews/", ComponentReviewListView.as_view(), name="component-reviews"),
    
    path("documents/<uuid:document_id>/access/", DocumentAccessListGrantView.as_view(), name="document-access"),
    path("documents/<uuid:document_id>/access/action/", DocumentAccessActionView.as_view(), name="document-access-action"),
]