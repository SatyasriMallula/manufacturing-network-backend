from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from core.responses import success_response
from core.pagination import StandardPagination
from core.permissions import IsCompanyAdmin, IsCompanyAdminOrSuperuser
from .models import Component, ComponentImage, ComponentDocument, ComponentDocumentAccess
from .serializers import (
    ComponentSerializer, ComponentImageSerializer, ComponentDocumentSerializer,
     
)
from django.utils import timezone
from django.db.models import Avg, Count, Q
import uuid

from core.permissions import has_role
from rfqs.models import RFQ, RFQRecipient

from orders.models import OrderReview
from orders.serializers import OrderReviewSerializer
from core.pagination import StandardPagination


def visible_documents(component, user):
    docs = component.documents.all()
    if user.is_superuser or user.organization_id == component.organization_id:
        return docs
    return docs.filter(
        Q(access_level=ComponentDocument.AccessLevel.PUBLIC)
        | Q(access_grants__granted_to_organization_id=user.organization_id,
            access_grants__is_revoked=False)
    ).distinct()



class ComponentReviewListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, component_id):
        component = get_object_or_404(Component, id=component_id)
        reviews = OrderReview.objects.filter(order__component=component).select_related(
            "order__buyer_organization", "reviewed_by"
        )
        paginator = StandardPagination()
        page = paginator.paginate_queryset(reviews, request)
        return success_response(
            message="Reviews fetched",
            data=OrderReviewSerializer(page, many=True).data,
            **paginator.get_pagination_meta(),
        )

class PublicComponentListView(APIView):
    """Any logged-in user can browse active components across all vendors."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        components = Component.objects.filter(
    status=Component.Status.ACTIVE,
    organization__compliance_info__verification_status="verified",
).annotate(avg_rating=Avg("orders__review__rating"), num_reviews=Count("orders__review"))

        params = request.query_params

        if params.get("organization"):
            components = components.filter(organization_id=params["organization"])
        if params.get("category"):
            components = components.filter(category__icontains=params["category"])
        if params.get("material"):
            components = components.filter(materials__icontains=params["material"])
        if params.get("process"):
            components = components.filter(manufacturing_processes__icontains=params["process"])
        if params.get("certification"):
            components = components.filter(certifications__icontains=params["certification"])
        if params.get("min_rating"):
            components = components.filter(avg_rating__gte=params["min_rating"])
        if params.get("search"):
            term = params["search"]
            components = components.filter(
                Q(name__icontains=term) | Q(description__icontains=term) | Q(sku__icontains=term)
            )

        ordering = params.get("ordering", "-created_at")
        if ordering in ["-created_at", "name", "-avg_rating", "typical_lead_time_days"]:
            components = components.order_by(ordering)

        paginator = StandardPagination()
        page = paginator.paginate_queryset(components, request)
        serializer = ComponentSerializer(page, many=True)

        return success_response(
            message="Components fetched",
            **paginator.get_pagination_meta(),
            data=serializer.data,
           
        )

# ---------- Component CRUD (Company Admin, own org only) ----------

class MyComponentListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdminOrSuperuser,]

    def get(self, request):
        components = Component.objects.filter(organization=request.user.organization).order_by("-created_at")
        return success_response(message="Components fetched", data=ComponentSerializer(components, many=True).data)

    def post(self, request):
        serializer = ComponentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        component = serializer.save(organization=request.user.organization)
        return success_response(
            message="Component added successfully",
            data=ComponentSerializer(component).data,
            status_code=201,
        )


class MyComponentDetailView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]

    def get_object(self, request, component_id):
        return get_object_or_404(Component, id=component_id, organization=request.user.organization)
    
    def get(self, request, component_id):
        component = self.get_object(request, component_id)
        serializer = ComponentSerializer(component)
        return success_response(message="Component fetched", data=serializer.data)

    def patch(self, request, component_id):
        component = self.get_object(request, component_id)
        serializer = ComponentSerializer(component, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return success_response(message="Component updated", data=serializer.data)

    def delete(self, request, component_id):
        component = self.get_object(request, component_id)
        component.delete()
        return success_response(message="Component deleted", data=None)


# ---------- Component Images (Company Admin, own org only) ----------

from rest_framework.parsers import MultiPartParser, FormParser, JSONParser


class ComponentImageListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request, component_id):
        component = get_object_or_404(Component, id=component_id, organization=request.user.organization)
        return success_response(
            data=ComponentImageSerializer(component.images.all(), many=True, context={"request": request}).data
        )

    def post(self, request, component_id):
        component = get_object_or_404(Component, id=component_id, organization=request.user.organization)
        serializer = ComponentImageSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        image = serializer.save(component=component, uploaded_by=request.user)
        return success_response(
            message="Image uploaded successfully",
            data=ComponentImageSerializer(image, context={"request": request}).data,
            status_code=201,
        )


class ComponentImageDeleteView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]

    def delete(self, request, component_id, image_id):
        image = get_object_or_404(
            ComponentImage, id=image_id, component_id=component_id,
            component__organization=request.user.organization,
        )
        image.image.delete(save=False)   # works for local + S3
        image.delete()
        return success_response(message="Image deleted", data=None)

# ---------- Component Documents (Company Admin, own org only) ----------
class ComponentDocumentListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, component_id):
        component = get_object_or_404(Component, id=component_id)
        docs = visible_documents(component, request.user)
        return success_response(data=ComponentDocumentSerializer(docs, many=True).data)

    def post(self, request, component_id):
        component = get_object_or_404(Component, id=component_id, organization=request.user.organization)
        if not has_role(request.user, "company_admin"):
            return success_response(message="Only Company Admin can upload documents", data=None, status_code=403)

        serializer = ComponentDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        doc = serializer.save(component=component, uploaded_by=request.user)
        return success_response(
            message="Document uploaded successfully",
            data=ComponentDocumentSerializer(doc).data,
            status_code=201,
        )


class ComponentDocumentDeleteView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]

    def delete(self, request, component_id, document_id):
        doc = get_object_or_404(
            ComponentDocument, id=document_id, component_id=component_id,
            component__organization=request.user.organization,
        )
        doc.file.delete(save=False)   # works for local + S3
        doc.delete()
        return success_response(message="Document deleted", data=None)

class DocumentAccessListGrantView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]

    def get(self, request, document_id):
        """List everyone who currently has access to this document. Owner only."""
        document = get_object_or_404(
            ComponentDocument, id=document_id,
            component__organization=request.user.organization,
        )
        grants = document.access_grants.filter(is_revoked=False)
        data = [
            {
                "organization_id": str(g.granted_to_organization_id),
                "organization_name": g.granted_to_organization.name,
                "decision": g.decision,
                "is_active": g.is_active(),
                "keep_until_completion": g.keep_until_completion,
                "granted_at": g.granted_at,
                "decided_at": g.decided_at,
            }
            for g in grants
        ]
        return success_response(data=data)

    def post(self, request, document_id):
        document = get_object_or_404(
            ComponentDocument, id=document_id,
            component__organization=request.user.organization,
        )
        try:
            rfq_id = uuid.UUID(str(request.data.get("rfq_id")))
        except ValueError:
            return success_response(message="A valid rfq_id is required", data=None, status_code=400)

        # 404 unless this vendor was actually invited to this RFQ
        recipient = get_object_or_404(
            RFQRecipient.objects.select_related("rfq__buyer_organization"),
            rfq_id=rfq_id, vendor_organization=request.user.organization,
        )
        rfq = recipient.rfq
        live_recipient = recipient.status in (
            RFQRecipient.Status.SENT, RFQRecipient.Status.VIEWED,
            RFQRecipient.Status.QUOTED, RFQRecipient.Status.AWARDED,
        )
        live_rfq = rfq.status in (RFQ.Status.OPEN, RFQ.Status.CLOSED, RFQ.Status.AWARDED)
        if not (live_recipient and live_rfq):
            return success_response(message="This RFQ is no longer active for you", data=None, status_code=400)

        access, _ = ComponentDocumentAccess.objects.update_or_create(
            document=document,
            granted_to_organization=rfq.buyer_organization,
            defaults={
                "granted_by": request.user, "rfq": rfq,
                "decision": ComponentDocumentAccess.Decision.PENDING, "decided_at": None,
                "keep_until_completion": False, "is_revoked": False, "revoked_at": None,
            },
        )
        return success_response(message="Access granted", data={"id": str(access.id)}, status_code=201)

class DocumentAccessActionView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, document_id):
        org_id = request.data.get("organization_id")
        action = request.data.get("action")  # "confirm", "reject", "revoke", "keep_until_completion"

        if not org_id or not action:
            return success_response(message="organization_id and action are required", data=None, status_code=400)

        access = get_object_or_404(
            ComponentDocumentAccess,
            document_id=document_id,
            granted_to_organization_id=org_id,
            is_revoked=False,
        )

        # buyer actions
        if action in ["confirm", "reject"]:
            if request.user.organization_id != access.granted_to_organization_id:
                return success_response(message="Not allowed", data=None, status_code=403)

            access.decision = (
                ComponentDocumentAccess.Decision.CONFIRMED if action == "confirm"
                else ComponentDocumentAccess.Decision.REJECTED
            )
            access.decided_at = timezone.now()
            if action == "reject":
                access.is_revoked = True
                access.revoked_at = timezone.now()
            access.save()
            return success_response(message=f"Design {action}ed")

        # vendor actions
        elif action in ["revoke", "keep_until_completion"]:
            if request.user.organization_id != access.document.component.organization_id:
                return success_response(message="Not allowed", data=None, status_code=403)

            if action == "revoke":
                access.is_revoked = True
                access.revoked_at = timezone.now()
            else:
                access.keep_until_completion = True
            access.save()
            return success_response(message=f"Access updated: {action}")

        return success_response(message="Invalid action", data=None, status_code=400)