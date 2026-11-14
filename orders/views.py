from datetime import date, timedelta

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from core.responses import success_response
from core.pagination import StandardPagination
from .models import Order, OrderStatusHistory, OrderReview
from .serializers import OrderSerializer, OrderDetailSerializer, OrderReviewSerializer
from .workflow import ACTIONS, actor_allowed
from notifications import events
from products.services import release_for_order_end
from billing.models import Invoice, Payment
from django.db import IntegrityError
from core.permissions import has_role, BUYER_ROLES

def orders_visible_to(user):
    """Buyer and vendor of an order can see it. Nobody else."""
    if user.is_superuser:
        return Order.objects.all()
    return Order.objects.filter(
        Q(buyer_organization=user.organization) | Q(vendor_organization=user.organization)
    )


class OrderListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        orders = orders_visible_to(request.user).select_related(
            "rfq", "buyer_organization", "vendor_organization", "product", "review"
        )
        org = request.user.organization
        params = request.query_params

        if params.get("view") == "purchases":
            orders = orders.filter(buyer_organization=org)
        elif params.get("view") == "sales":
            orders = orders.filter(vendor_organization=org)
        if params.get("status"):
            orders = orders.filter(status=params["status"])

        paginator = StandardPagination()
        page = paginator.paginate_queryset(orders, request)
        serializer = OrderSerializer(page, many=True, context={"request": request})
        return success_response(
            message="Orders fetched",
            data=serializer.data,
            **paginator.get_pagination_meta(),
        )


class OrderDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        order = get_object_or_404(
            orders_visible_to(request.user).select_related(
                "rfq", "buyer_organization", "vendor_organization", "product", "review"
            ).prefetch_related("history__changed_by"),
            id=order_id,
        )
        return success_response(data=OrderDetailSerializer(order, context={"request": request}).data)

    def patch(self, request, order_id):
        """One endpoint for every status change. Body: {"action": "...", "note": "..."}"""
        action_name = request.data.get("action")
        rule = ACTIONS.get(action_name)
        if not rule:
            return success_response(
                message=f"Invalid action. Use one of: {', '.join(ACTIONS)}", data=None, status_code=400
            )
        note = (request.data.get("note") or "").strip()

        with transaction.atomic():
            order = get_object_or_404(
                orders_visible_to(request.user).select_for_update(), id=order_id
            )
            if not actor_allowed(order, request.user, rule):
                return success_response(message="Not allowed", data=None, status_code=403)
            if order.status not in rule["from"]:
                return success_response(
                    message=f"Cannot {action_name} an order that is {order.status}", data=None, status_code=400
                )
            if action_name == "cancel" and not note:
                return success_response(message="A reason is required to cancel", data=None, status_code=400)
                        
            if action_name == "cancel":
                if Payment.objects.filter(invoice__order=order).exclude(status=Payment.Status.REJECTED).exists():
                    return success_response(
                        message="Payments exist for this order. Resolve them before cancelling.",
                        data=None, status_code=400,
                    )
                # No money has moved, so unpaid invoices are cancelled along with the order
                order.invoices.filter(status=Invoice.Status.ISSUED).update(status=Invoice.Status.CANCELLED)

            old_status = order.status
            order.status = rule["to"]
            update_fields = ["status", "updated_at"]

            if action_name == "confirm":
                order.expected_delivery_date = date.today() + timedelta(days=order.delivery_days)
                update_fields.append("expected_delivery_date")
            elif action_name == "ship" and request.data.get("shipping_reference"):
                order.shipping_reference = str(request.data["shipping_reference"])[:100]
                update_fields.append("shipping_reference")
            elif action_name == "cancel":
                order.cancellation_reason = note
                update_fields.append("cancellation_reason")

            order.save(update_fields=update_fields)
            OrderStatusHistory.objects.create(
                order=order, from_status=old_status, to_status=order.status,
                changed_by=request.user, note=note,
            )
            if order.status in (Order.Status.COMPLETED, Order.Status.CANCELLED):
                release_for_order_end(order)
            events.order_updated(order, old_status, request.user, note)

        order = get_object_or_404(
            Order.objects.select_related("rfq", "buyer_organization", "vendor_organization", "product")
            .prefetch_related("history__changed_by"),
            id=order.id,
        )
        return success_response(
            message="Order updated", data=OrderDetailSerializer(order, context={"request": request}).data
        )
    


class OrderReviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        order = get_object_or_404(orders_visible_to(request.user), id=order_id)
        review = OrderReview.objects.filter(order=order).select_related("order__buyer_organization").first()
        return success_response(data=OrderReviewSerializer(review).data if review else None)

    def post(self, request, order_id):
        # 404 unless the caller's org is the buyer of this order
        order = get_object_or_404(Order, id=order_id, buyer_organization=request.user.organization)
        if not has_role(request.user, *BUYER_ROLES):
            return success_response(message="Not allowed", data=None, status_code=403)
        if order.status != Order.Status.COMPLETED:
            return success_response(message="You can review an order only after it is completed", data=None, status_code=400)

        serializer = OrderReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            review = serializer.save(order=order, reviewed_by=request.user)
        except IntegrityError:
            return success_response(message="This order has already been reviewed", data=None, status_code=400)
        return success_response(message="Review submitted", data=OrderReviewSerializer(review).data, status_code=201)