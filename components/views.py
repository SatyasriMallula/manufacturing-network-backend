from urllib import request

from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from core.responses import success_response
from core.pagination import StandardPagination
from core.permissions import IsCompanyAdmin, IsCompanyAdminOrSuperuser
from .models import Component, ComponentImage, ComponentDocument, ComponentDocumentAccess
from .serializers import (
    ComponentSerializer
     
)
from django.utils import timezone
from django.db.models import Avg, Count, Q
import uuid

from core.permissions import has_role
from rfqs.models import RFQ, RFQRecipient

from orders.models import OrderReview
from orders.serializers import OrderReviewSerializer
from core.pagination import StandardPagination

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.permissions import has_role
from core.responses import error_response, success_response
from uploads import services
from uploads.models import FileAsset
from uploads.policies import REGISTRY
from .models import Component, ComponentDocument, ComponentDocumentAccess, ComponentImage
from .serializers import AttachDocumentSerializer, AttachImageSerializer
from uploads import s3  
from django.db.models import F


DOC_CATEGORIES = [FileAsset.Category.DRAWING, FileAsset.Category.SPECIFICATION, FileAsset.Category.OTHER]


def _not_admin(request):
    if not has_role(request.user, "company_admin"):
        return error_response("Not allowed", status_code=403)


def _image_data(image):
    asset = image.file_asset
    return {
        "id": str(image.id),
        "file_asset_id": str(image.file_asset_id) if image.file_asset_id else None,
        "filename": asset.original_filename if asset else None,
        "size_bytes": asset.size_bytes if asset else None,
        "is_primary": image.is_primary, "display_order": image.display_order, "created_at": image.created_at,
    }


def _document_data(doc):
    asset = doc.file_asset
    return {
        "id": str(doc.id),
        "file_asset_id": str(doc.file_asset_id) if doc.file_asset_id else None,
        "doc_type": doc.doc_type, "title": doc.title,
        "filename": asset.original_filename if asset else None,
        "size_bytes": asset.size_bytes if asset else None,
        "created_at": doc.created_at,
    }


def _visible_documents(component, user):
    docs = component.documents.select_related("file_asset")
    if user.is_superuser or user.organization_id == component.organization_id:
        return docs
    granted = ComponentDocumentAccess.objects.filter(
        granted_to_organization_id=user.organization_id, is_revoked=False,
    ).exclude(decision=ComponentDocumentAccess.Decision.REJECTED)
    return docs.filter(access_grants__in=granted).distinct()

class ComponentImageListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, component_id):
        denied = _not_admin(request)
        if denied:
            return denied
        component = get_object_or_404(Component, id=component_id, organization=request.user.organization)
        images = component.images.select_related("file_asset")
        return success_response(data=[_image_data(i) for i in images])

    def post(self, request, component_id):
        denied = _not_admin(request)
        if denied:
            return denied
        component = get_object_or_404(Component, id=component_id, organization=request.user.organization)
        serializer = AttachImageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        asset = FileAsset.objects.active().filter(
            id=data["file_asset_id"], organization=request.user.organization,
            component=component, category=FileAsset.Category.IMAGE,
        ).first()
        if asset is None:
            return error_response("File not found for this component", status_code=400)
        if ComponentImage.objects.filter(file_asset=asset).exists():
            return error_response("This file is already attached", status_code=400)

        with transaction.atomic():
            is_primary = data["is_primary"] or not component.images.exists()   # the first image becomes the main one
            if is_primary:
                component.images.filter(is_primary=True).update(is_primary=False)
            image = ComponentImage.objects.create(
                component=component, uploaded_by=request.user, file_asset=asset,
                is_primary=is_primary,
                display_order=data["display_order"], status=ComponentImage.Status.READY,
            )
        return success_response(message="Image added", data=_image_data(image), status_code=201)


class ComponentImageDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _image(self, request, component_id, image_id):
        return get_object_or_404(
            ComponentImage.objects.select_related("file_asset"),
            id=image_id, component_id=component_id,
            component__organization=request.user.organization,
        )

    def patch(self, request, component_id, image_id):
        denied = _not_admin(request)
        if denied:
            return denied
        image = self._image(request, component_id, image_id)
        serializer = AttachImageSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            if data.get("is_primary"):
                image.component.images.exclude(pk=image.pk).update(is_primary=False)
                image.is_primary = True
            if "display_order" in data:
                image.display_order = data["display_order"]
            image.save(update_fields=["is_primary", "display_order"])
        return success_response(message="Image updated", data=_image_data(image))

    def delete(self, request, component_id, image_id):
        denied = _not_admin(request)
        if denied:
            return denied
        image = self._image(request, component_id, image_id)
        if image.file_asset_id:
            services.delete_file_asset(image.file_asset)   # also removes this row
        else:
            image.delete()                                  # an old image with no FileAsset
        return success_response(message="Image deleted", data=None)


class ComponentDocumentListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, component_id):
        component = REGISTRY["component"].get_parent(request.user, component_id)
        if component is None:
            return error_response("Not found", status_code=404)
        docs = _visible_documents(component, request.user)
        return success_response(data=[_document_data(d) for d in docs])

    def post(self, request, component_id):
        denied = _not_admin(request)
        if denied:
            return denied
        component = get_object_or_404(Component, id=component_id, organization=request.user.organization)
        serializer = AttachDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        asset = FileAsset.objects.active().filter(
            id=data["file_asset_id"], organization=request.user.organization,
            component=component, category__in=DOC_CATEGORIES,
        ).first()
        if asset is None:
            return error_response("File not found for this component", status_code=400)
        if ComponentDocument.objects.filter(file_asset=asset).exists():
            return error_response("This file is already attached", status_code=400)

        doc = ComponentDocument.objects.create(
            component=component, uploaded_by=request.user, file_asset=asset,
            doc_type=data["doc_type"], title=data["title"],
            status=ComponentDocument.Status.READY,
        )
        return success_response(message="Document added", data=_document_data(doc), status_code=201)


class ComponentDocumentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, component_id, document_id):
        denied = _not_admin(request)
        if denied:
            return denied
        doc = get_object_or_404(
            ComponentDocument, id=document_id, component_id=component_id,
            component__organization=request.user.organization,
        )
        if doc.file_asset_id:
            services.delete_file_asset(doc.file_asset)
        else:
            doc.delete()
        return success_response(message="Document deleted", data=None)


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
        if ordering == "-avg_rating":
            components = components.order_by(F("avg_rating").desc(nulls_last=True), "id")
        elif ordering in ("-created_at", "name", "typical_lead_time_days"):
            components = components.order_by(ordering, "id")
        else:
            components = components.order_by("-created_at", "id")

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
        if not request.user.organization:
            return error_response("Your account is not linked to an organization", status_code=400)
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
        keys = list(FileAsset.objects.filter(component=component).values_list("object_key", flat=True))

        def remove_objects():
            for key in keys:
                try:
                    s3.delete_object(key)
                except Exception:
                    pass   # a leftover object is picked up by cleanup_uploads

        with transaction.atomic():
            component.delete()
            transaction.on_commit(remove_objects)
        return success_response(message="Component deleted", data=None)

class DocumentAccessListGrantView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]

    def get(self, request, document_id):
        """List everyone who currently has access to this document. Owner only."""
        document = get_object_or_404(
            ComponentDocument, id=document_id,
            component__organization=request.user.organization,
        )
        grants = document.access_grants.filter(is_revoked=False).select_related("granted_to_organization", "rfq")
        data = [
            {
                "organization_id": str(g.granted_to_organization_id),
                "organization_name": g.granted_to_organization.name,
                "decision": g.decision,
                "is_active": g.is_active(),
                "keep_until_completion": g.keep_until_completion,
                "granted_at": g.granted_at,
                "decided_at": g.decided_at,
                "rfq_number": g.rfq.rfq_number if g.rfq else None,
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
        action = request.data.get("action")
        try:
            org_id = uuid.UUID(str(request.data.get("organization_id")))
        except ValueError:
            return error_response("A valid organization_id is required", status_code=400)
        if not action:
            return error_response("action is required", status_code=400)
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