import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import  transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from core.pagination import StandardPagination
from core.permissions import has_role, FINANCE_ROLES
from core.responses import success_response,error_response
from orders.models import Order
from .models import Invoice, Payment
from .serializers import InvoiceSerializer, InvoiceCreateSerializer, PaymentSerializer

ZERO = Decimal("0.00")


def invoices_visible_to(user):
    if user.is_superuser:
        return Invoice.objects.all()
    return Invoice.objects.filter(
        Q(vendor_organization=user.organization) | Q(buyer_organization=user.organization)
    )


def _detail_qs():
    return Invoice.objects.select_related(
        "order", "vendor_organization", "buyer_organization"
    ).prefetch_related("payments")


class InvoiceListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        invoices = invoices_visible_to(request.user).select_related(
            "order", "vendor_organization", "buyer_organization"
        ).prefetch_related("payments")
        org = request.user.organization
        params = request.query_params
        if params.get("order"):
            try:
                invoices = invoices.filter(order_id=uuid.UUID(params["order"]))
            except ValueError:
                return error_response(message="Invalid order id", data=None, status_code=400)
        if params.get("view") == "issued":
            invoices = invoices.filter(vendor_organization=org)
        elif params.get("view") == "received":
            invoices = invoices.filter(buyer_organization=org)
        if params.get("status"):
            invoices = invoices.filter(status=params["status"])

        paginator = StandardPagination()
        page = paginator.paginate_queryset(invoices, request)
        return success_response(
            message="Invoices fetched",
            data=InvoiceSerializer(page, many=True).data,
            **paginator.get_pagination_meta(),
        )

    def post(self, request):
        """Vendor issues an invoice (advance, progress, or final) against an order."""
        if not has_role(request.user, *FINANCE_ROLES):
            return success_response(message="Not allowed", data=None, status_code=403)

        serializer = InvoiceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            # Lock the order, so two simultaneous invoices can't both fit in the same remaining balance
            order = get_object_or_404(
                Order.objects.select_for_update(),
                id=data["order_id"], vendor_organization=request.user.organization,
            )
            if order.status in (Order.Status.PLACED, Order.Status.CANCELLED):
                return success_response(
                    message="Invoices can be issued once the order is confirmed and not cancelled",
                    data=None, status_code=400,
                )

            invoiced = order.invoices.exclude(status=Invoice.Status.CANCELLED).aggregate(
                s=Sum("subtotal")
            )["s"] or ZERO
            remaining = order.total_price - invoiced
            if remaining <= ZERO:
                return success_response(message="This order is already fully invoiced", data=None, status_code=400)

            if data.get("amount") is not None:
                subtotal = data["amount"]
            elif data.get("percent") is not None:
                subtotal = (order.total_price * data["percent"] / Decimal("100")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            else:  # final invoice with no amount: bill whatever is left
                subtotal = remaining

            if subtotal <= ZERO or subtotal > remaining:
                return success_response(
                    message=f"Invoice amount must be between 0.01 and the remaining balance of {remaining}",
                    data=None, status_code=400,
                )

            tax = (subtotal * data["tax_percent"] / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            invoice = Invoice.objects.create(
                order=order,
                vendor_organization=order.vendor_organization,
                buyer_organization=order.buyer_organization,
                issued_by=request.user,
                invoice_type=data["invoice_type"],
                description=data["description"],
                subtotal=subtotal, tax_percent=data["tax_percent"],
                tax_amount=tax, total_amount=subtotal + tax,
                currency=order.currency,
                due_date=timezone.localdate() + timedelta(days=data["due_in_days"]),
                notes=data["notes"],
            )

        invoice = _detail_qs().get(id=invoice.id)
        return success_response(message="Invoice issued", data=InvoiceSerializer(invoice).data, status_code=201)

class InvoiceDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, invoice_id):
        invoice = get_object_or_404(invoices_visible_to(request.user).select_related(
            "order", "vendor_organization", "buyer_organization"
        ).prefetch_related("payments"), id=invoice_id)
        return success_response(data=InvoiceSerializer(invoice).data)

    def patch(self, request, invoice_id):
        """Body: {"action": "cancel"}. Vendor only, and only while nothing has been paid."""
        if request.data.get("action") != "cancel":
            return success_response(message="Invalid action. Use 'cancel'.", data=None, status_code=400)
        if not has_role(request.user, *FINANCE_ROLES):
            return success_response(message="Not allowed", data=None, status_code=403)

        with transaction.atomic():
            invoice = get_object_or_404(
                Invoice.objects.select_for_update(),
                id=invoice_id, vendor_organization=request.user.organization,
            )
            if invoice.status != Invoice.Status.ISSUED:
                return success_response(message="Only an issued, unpaid invoice can be cancelled", data=None, status_code=400)
            if invoice.payments.exclude(status=Payment.Status.REJECTED).exists():
                return success_response(message="This invoice has payments recorded against it", data=None, status_code=400)
            invoice.status = Invoice.Status.CANCELLED
            invoice.save(update_fields=["status", "updated_at"])

        invoice = _detail_qs().get(id=invoice.id)
        return success_response(message="Invoice cancelled", data=InvoiceSerializer(invoice).data)


class InvoicePaymentsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, invoice_id):
        """Buyer records a payment they made."""
        if not has_role(request.user, *FINANCE_ROLES):
            return success_response(message="Not allowed", data=None, status_code=403)

        serializer = PaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amount = serializer.validated_data["amount"]

        with transaction.atomic():
            invoice = get_object_or_404(
                Invoice.objects.select_for_update(),
                id=invoice_id, buyer_organization=request.user.organization,
            )
            if invoice.status not in (Invoice.Status.ISSUED, Invoice.Status.PARTIALLY_PAID):
                return success_response(message="This invoice is not open for payment", data=None, status_code=400)

            committed = invoice.payments.exclude(status=Payment.Status.REJECTED).aggregate(
                s=Sum("amount")
            )["s"] or ZERO
            if amount > invoice.total_amount - committed:
                return success_response(message="Amount exceeds the outstanding balance", data=None, status_code=400)

            payment = serializer.save(invoice=invoice, recorded_by=request.user)

        return success_response(
            message="Payment recorded, waiting for the vendor to confirm",
            data=PaymentSerializer(payment).data, status_code=201,
        )

    def patch(self, request, invoice_id):
        """Vendor confirms or rejects a payment. Body: {"payment_id": "...", "action": "confirm"|"reject"}"""
        if not has_role(request.user, *FINANCE_ROLES):
            return success_response(message="Not allowed", data=None, status_code=403)
        action = request.data.get("action")
        if action not in ("confirm", "reject"):
            return success_response(message="Invalid action. Use 'confirm' or 'reject'.", data=None, status_code=400)
        try:
            payment_id = uuid.UUID(str(request.data.get("payment_id")))
        except ValueError:
            return success_response(message="A valid payment_id is required", data=None, status_code=400)

        with transaction.atomic():
            invoice = get_object_or_404(
                Invoice.objects.select_for_update(),
                id=invoice_id, vendor_organization=request.user.organization,
            )
            payment = get_object_or_404(Payment, id=payment_id, invoice=invoice)
            if payment.status != Payment.Status.PENDING:
                return success_response(message="This payment has already been decided", data=None, status_code=400)

            payment.status = Payment.Status.CONFIRMED if action == "confirm" else Payment.Status.REJECTED
            payment.decided_by = request.user
            payment.decided_at = timezone.now()
            payment.save(update_fields=["status", "decided_by", "decided_at"])

            if action == "confirm":
                invoice.paid_amount = invoice.payments.filter(status=Payment.Status.CONFIRMED).aggregate(
                    s=Sum("amount")
                )["s"] or ZERO
                invoice.status = (
                    Invoice.Status.PAID if invoice.paid_amount >= invoice.total_amount
                    else Invoice.Status.PARTIALLY_PAID
                )
                invoice.save(update_fields=["paid_amount", "status", "updated_at"])

        invoice = _detail_qs().get(id=invoice.id)
        return success_response(message=f"Payment {action}ed", data=InvoiceSerializer(invoice).data)