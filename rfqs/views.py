from django.utils import timezone
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from core.responses import success_response
from core.pagination import StandardPagination
from core.permissions import has_role, BUYER_ROLES, VENDOR_ROLES
from .models import RFQ, RFQRecipient, RFQAttachment, Quote
from .serializers import (
    RFQSerializer, RFQAttachmentSerializer, RFQAttachmentCreateSerializer, QuoteSerializer,
)
from uploads.models import FileAsset
from uploads.services import delete_file_asset
import uuid
from datetime import date
from orders.services import create_order_from_award
from notifications import events
from components.services import revoke_for_rfq_awarded, revoke_for_rfq_cancelled

ALLOWED_TRANSITIONS = {
    "draft": {"open", "cancelled"},
    "open": {"closed", "cancelled"},
    "closed": {"awarded"},
    "awarded": set(),
    "cancelled": set(),
}


def rfqs_visible_to(user):
    """Buyer org sees its own RFQs. Vendor orgs see RFQs sent to them, never drafts."""
    if user.is_superuser:
        return RFQ.objects.all()
    return RFQ.objects.filter(
        Q(buyer_organization=user.organization)
        | (Q(recipients__vendor_organization=user.organization) & ~Q(status=RFQ.Status.DRAFT))
    ).distinct()


class RFQListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rfqs = (
            rfqs_visible_to(request.user)
            .select_related("buyer_organization")
            .prefetch_related(
                "recipients__vendor_organization", "recipients__component", "attachments__file_asset",
            )
        )
        org = request.user.organization
        params = request.query_params

        if params.get("view") == "sent":
            rfqs = rfqs.filter(buyer_organization=org)
        elif params.get("view") == "received":
            rfqs = rfqs.filter(recipients__vendor_organization=org).exclude(status=RFQ.Status.DRAFT).distinct()
        if params.get("status"):
            rfqs = rfqs.filter(status=params["status"])

        paginator = StandardPagination()
        page = paginator.paginate_queryset(rfqs, request)
        serializer = RFQSerializer(page, many=True, context={"request": request})
        return success_response(
            message="RFQs fetched",
            **paginator.get_pagination_meta(),
            data=serializer.data,            
        )

    def post(self, request):
        if not request.user.organization:
            return success_response(message="Your account is not linked to an organization", data=None, status_code=400)
        if not request.user.organization.is_verified:
            return success_response(message="Your organization must be verified before raising RFQs", data=None, status_code=403)
        if not has_role(request.user, *BUYER_ROLES):
            return success_response(message="Not allowed", data=None, status_code=403)

        serializer = RFQSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        rfq = serializer.save()
        if rfq.status == RFQ.Status.OPEN:
            events.rfq_sent(rfq, request.user)
        return success_response(
            message="RFQ created successfully",
            data=RFQSerializer(rfq, context={"request": request}).data,
            status_code=201,
        )


class RFQDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_rfq(self, request, rfq_id):
        return get_object_or_404(rfqs_visible_to(request.user), id=rfq_id)

    def get(self, request, rfq_id):
        rfq = self.get_rfq(request, rfq_id)
        if rfq.buyer_organization_id != request.user.organization_id:
            rfq.recipients.filter(
                vendor_organization=request.user.organization, status=RFQRecipient.Status.SENT
            ).update(status=RFQRecipient.Status.VIEWED)
        return success_response(data=RFQSerializer(rfq, context={"request": request}).data)

    def patch(self, request, rfq_id):
        rfq = self.get_rfq(request, rfq_id)

        if rfq.buyer_organization_id == request.user.organization_id:
            return self._buyer_update(request, rfq)
        if request.data.get("action") == "decline":
            return self._vendor_decline(request, rfq)
        return success_response(message="Not allowed", data=None, status_code=403)

    def _buyer_update(self, request, rfq):
        if not has_role(request.user, *BUYER_ROLES):
            return success_response(message="Not allowed", data=None, status_code=403)

        new_status = request.data.get("status")
        other_fields = set(request.data.keys()) - {"status"}

        if rfq.status != RFQ.Status.DRAFT and other_fields:
            return success_response(message="Only draft RFQs can be edited", data=None, status_code=400)
        if new_status and new_status != rfq.status and new_status not in ALLOWED_TRANSITIONS[rfq.status]:
            return success_response(
                message=f"Cannot change status from {rfq.status} to {new_status}", data=None, status_code=400
            )
        old_status = rfq.status
        serializer = RFQSerializer(rfq, data=request.data, partial=True, context={"request": request})
        if request.data.get("status") == RFQ.Status.OPEN and not request.user.organization.is_verified:
            return success_response(message="Your organization must be verified before sending RFQs", data=None, status_code=403)
        serializer.is_valid(raise_exception=True)
        rfq = serializer.save()
        if rfq.status == RFQ.Status.CANCELLED:
            revoke_for_rfq_cancelled(rfq)
        if old_status != rfq.status:
            if rfq.status == RFQ.Status.OPEN:
                events.rfq_sent(rfq, request.user)
            elif rfq.status in (RFQ.Status.CLOSED, RFQ.Status.CANCELLED):
                events.rfq_closed_or_cancelled(rfq, request.user)
        return success_response(message="RFQ updated", data=RFQSerializer(rfq, context={"request": request}).data)

    def _vendor_decline(self, request, rfq):
        if not has_role(request.user, *VENDOR_ROLES):
            return success_response(message="Not allowed", data=None, status_code=403)

        recipient = get_object_or_404(RFQRecipient, rfq=rfq, vendor_organization=request.user.organization)
        if rfq.status != RFQ.Status.OPEN or recipient.status not in (
            RFQRecipient.Status.SENT, RFQRecipient.Status.VIEWED
        ):
            return success_response(message="This RFQ can no longer be declined", data=None, status_code=400)

        recipient.status = RFQRecipient.Status.DECLINED
        recipient.save()
        events.rfq_declined(rfq, recipient, request.user)
        return success_response(message="RFQ declined")


class RFQAttachmentCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, rfq_id):
        rfq = get_object_or_404(RFQ, id=rfq_id, buyer_organization=request.user.organization)
        if not has_role(request.user, *BUYER_ROLES):
            return success_response(message="Not allowed", data=None, status_code=403)
        if rfq.status not in (RFQ.Status.DRAFT, RFQ.Status.OPEN):
            return success_response(message="Attachments can only be added to draft or open RFQs", data=None, status_code=400)

        serializer = RFQAttachmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        asset = FileAsset.objects.active().exclude(
            scan_status=FileAsset.ScanStatus.REJECTED
        ).filter(
            id=data["file_asset_id"],
            organization=request.user.organization,
            rfq=rfq,
            category__in=(
                FileAsset.Category.RFQ_ATTACHMENT,
                FileAsset.Category.DRAWING,
                FileAsset.Category.SPECIFICATION,
                FileAsset.Category.OTHER,
            ),
        ).first()
        if asset is None:
            return success_response(message="File not found for this RFQ", data=None, status_code=400)
        if RFQAttachment.objects.filter(file_asset=asset).exists():
            return success_response(message="This file is already attached", data=None, status_code=400)

        attachment = RFQAttachment.objects.create(
            rfq=rfq, uploaded_by=request.user, file_asset=asset, title=data["title"],
        )
        return success_response(
            message="Attachment uploaded",
            data=RFQAttachmentSerializer(attachment).data,
            status_code=201,
        )


class RFQAttachmentDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, rfq_id, attachment_id):
        attachment = get_object_or_404(
            RFQAttachment, id=attachment_id, rfq_id=rfq_id,
            rfq__buyer_organization=request.user.organization,
        )
        if not has_role(request.user, *BUYER_ROLES):
            return success_response(message="Not allowed", data=None, status_code=403)
        if attachment.rfq.status != RFQ.Status.DRAFT:
            return success_response(message="Attachments can only be removed while the RFQ is a draft", data=None, status_code=400)

        if attachment.file_asset_id:
            delete_file_asset(attachment.file_asset)
        else:
            attachment.delete()
        return success_response(message="Attachment deleted", data=None)


class RFQAwardView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, rfq_id):
        if not has_role(request.user, *BUYER_ROLES):
            return success_response(message="Not allowed", data=None, status_code=403)

        try:
            vendor_id = uuid.UUID(str(request.data.get("vendor_organization")))
        except ValueError:
            return success_response(message="A valid vendor_organization is required", data=None, status_code=400)

        with transaction.atomic():
            rfq = get_object_or_404(
                RFQ.objects.select_for_update(),  # locks the row, so two awards can't both win
                id=rfq_id, buyer_organization=request.user.organization,
            )
            if rfq.status not in (RFQ.Status.OPEN, RFQ.Status.CLOSED):
                return success_response(message="This RFQ can no longer be awarded", data=None, status_code=400)
            if not rfq.quotes_visible_to_buyer():
                return success_response(message="Sealed bids: award after the deadline", data=None, status_code=400)

            recipient = get_object_or_404(
                RFQRecipient.objects.select_related("quote"),
                rfq=rfq, vendor_organization_id=vendor_id,
            )
            if recipient.status != RFQRecipient.Status.QUOTED:
                return success_response(message="Only vendors who submitted a quote can be awarded", data=None, status_code=400)
            if recipient.quote.valid_until and recipient.quote.valid_until < date.today():
                return success_response(message="This quote has expired", data=None, status_code=400)

            rfq.status = RFQ.Status.AWARDED
            rfq.awarded_recipient = recipient
            rfq.awarded_at = timezone.now()
            rfq.save(update_fields=["status", "awarded_recipient", "awarded_at", "updated_at"])

            recipient.status = RFQRecipient.Status.AWARDED
            recipient.save(update_fields=["status"])
            rfq.recipients.exclude(pk=recipient.pk).exclude(
                status=RFQRecipient.Status.DECLINED
            ).update(status=RFQRecipient.Status.NOT_SELECTED)
            order = create_order_from_award(rfq, recipient, request.user)
            revoke_for_rfq_awarded(rfq, recipient.vendor_organization_id)
            events.rfq_awarded(rfq, recipient, order, request.user)
            
        rfq_data = RFQSerializer(rfq, context={"request": request}).data
        return success_response(
            message="RFQ awarded. Order placed.",
            data={**rfq_data, "order": {"id": str(order.id), "order_number": order.order_number}},
        )
        
    
class RFQQuoteView(APIView):
    permission_classes = [IsAuthenticated]

    def _recipient(self, request, rfq_id):
        # 404 unless this user's org was actually invited to this RFQ
        return get_object_or_404(
            RFQRecipient.objects.select_related("rfq"),
            rfq_id=rfq_id, vendor_organization=request.user.organization,
        )

    def get(self, request, rfq_id):
        recipient = self._recipient(request, rfq_id)
        quote = get_object_or_404(Quote, recipient=recipient)
        return success_response(data=QuoteSerializer(quote).data)

    def post(self, request, rfq_id):
        if not has_role(request.user, *VENDOR_ROLES):
            return success_response(message="Not allowed", data=None, status_code=403)
        if not request.user.organization.is_verified:
            return success_response(message="Your organization must be verified before quoting", data=None, status_code=403)
        recipient = self._recipient(request, rfq_id)

        if not recipient.rfq.accepting_quotes():                      # CHANGED
            return success_response(message="This RFQ is no longer accepting quotes", data=None, status_code=400)
        if recipient.status == RFQRecipient.Status.DECLINED:
            return success_response(message="You declined this RFQ", data=None, status_code=400)
        if recipient.status == RFQRecipient.Status.QUOTED:
            return success_response(message="Quote already submitted. Use PATCH to revise it", data=None, status_code=400)

        serializer = QuoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            quote = serializer.save(recipient=recipient, submitted_by=request.user)   # CHANGED
            recipient.status = RFQRecipient.Status.QUOTED
            recipient.save(update_fields=["status"])
        events.quote_received(recipient.rfq, False, request.user)
        return success_response(message="Quote submitted", data=QuoteSerializer(quote).data, status_code=201)

    def patch(self, request, rfq_id):
        if not has_role(request.user, *VENDOR_ROLES):
            return success_response(message="Not allowed", data=None, status_code=403)

        recipient = self._recipient(request, rfq_id)

        if not recipient.rfq.accepting_quotes():                      # CHANGED
            return success_response(message="This RFQ is no longer accepting quotes", data=None, status_code=400)

        quote = get_object_or_404(Quote, recipient=recipient)
        if recipient.status != RFQRecipient.Status.QUOTED:
            return success_response(message="This quote can no longer be changed", data=None, status_code=400)

        serializer = QuoteSerializer(quote, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        quote = serializer.save()
        events.quote_received(recipient.rfq, True, request.user)
        return success_response(message="Quote updated", data=QuoteSerializer(quote).data)
    
class RFQQuoteListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, rfq_id):
        rfq = get_object_or_404(RFQ, id=rfq_id, buyer_organization=request.user.organization)
        if not has_role(request.user, *BUYER_ROLES):
            return success_response(message="Not allowed", data=None, status_code=403)

        if not rfq.quotes_visible_to_buyer():                         # CHANGED
            return success_response(
                message="Quotes are hidden until the deadline (sealed bids)", data=None, status_code=400
            )

        quotes = (
            Quote.objects.filter(recipient__rfq=rfq)
            .select_related("recipient__vendor_organization", "recipient__rfq")
            .order_by("unit_price")
        )
        return success_response(message="Quotes fetched", data=QuoteSerializer(quotes, many=True).data)
