from django.urls import path
from .views import InvoiceListCreateView, InvoiceDetailView, InvoicePaymentsView

urlpatterns = [
    path("invoices/", InvoiceListCreateView.as_view(), name="invoice-list-create"),
    path("invoices/<uuid:invoice_id>/", InvoiceDetailView.as_view(), name="invoice-detail"),
    path("invoices/<uuid:invoice_id>/payments/", InvoicePaymentsView.as_view(), name="invoice-payments"),
]