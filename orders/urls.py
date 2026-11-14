from django.urls import path
from .views import OrderListView, OrderDetailView, OrderReviewView

urlpatterns = [
    path("orders/", OrderListView.as_view(), name="order-list"),
    path("orders/<uuid:order_id>/", OrderDetailView.as_view(), name="order-detail"),
    path("orders/<uuid:order_id>/review/", OrderReviewView.as_view(), name="order-review"),
]