from django.urls import path
from .views import (
    MyProductListCreateView, MyProductDetailView,
    ProductImageListCreateView, ProductImageDeleteView,
    ProductDocumentListCreateView, ProductDocumentDeleteView,
    ProductReviewListView, PublicProductListView,
)

from .views import DocumentAccessListGrantView, DocumentAccessActionView

urlpatterns = [
    path("products/", PublicProductListView.as_view(), name="product-list"),

    path("products/my/", MyProductListCreateView.as_view(), name="my-products"),
    path("products/my/<uuid:product_id>/", MyProductDetailView.as_view(), name="my-product-detail"),

    path("products/<uuid:product_id>/images/", ProductImageListCreateView.as_view(), name="product-images"),
    path("products/<uuid:product_id>/images/<uuid:image_id>/", ProductImageDeleteView.as_view(), name="product-image-delete"),

    path("products/<uuid:product_id>/documents/", ProductDocumentListCreateView.as_view(), name="product-documents"),
    path("products/<uuid:product_id>/documents/<uuid:document_id>/", ProductDocumentDeleteView.as_view(), name="product-document-delete"),

    path("products/<uuid:product_id>/reviews/", ProductReviewListView.as_view(), name="product-reviews"),
    
    path("documents/<uuid:document_id>/access/", DocumentAccessListGrantView.as_view(), name="document-access"),
    path("documents/<uuid:document_id>/access/action/", DocumentAccessActionView.as_view(), name="document-access-action"),
]