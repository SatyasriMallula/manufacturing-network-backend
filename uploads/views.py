import logging

from django.core import signing
from django.db import IntegrityError, transaction
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.responses import error_response, success_response
from . import s3, services
from .models import FileAsset
from .policies import REGISTRY
from .serializers import CompleteRequestSerializer, FileAssetSerializer, PresignRequestSerializer
from .validators import matches_signature
from django.conf import settings
from django.utils import timezone

from core.pagination import StandardPagination
from .serializers import FileListQuerySerializer

logger = logging.getLogger(__name__)


class PresignView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PresignRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = request.user

        if not user.organization_id:
            return error_response("Your account is not linked to an organization", status_code=403)

        policy = REGISTRY[data["entity_type"]]
        parent = policy.get_parent(user, data["entity_id"])
        if parent is None:
            return error_response("Not found", status_code=404)
        if not policy.can_upload(user, parent, data["category"]):
            return error_response("You cannot upload this file here", status_code=403)

        results = []
        for info in data["files"]:
            key = services.build_object_key(user.organization_id, policy.folder, parent.pk, info["ext"])
            results.append({
                "upload_url": s3.presign_put(key, info["content_type"], info["size_bytes"]),
                "method": "PUT",
                # The browser must send exactly this Content-Type, or S3 rejects the upload
                "headers": {"Content-Type": info["content_type"]},
                "object_key": key,
                "upload_token": services.issue_upload_token(user, key, policy.entity_type, parent.pk, data["category"], info),
                "expires_in": 900,
                "filename": info["filename"],
            })

        # One object for a single file, a list (same order) for a bulk request
        return success_response(
            message="Upload URLs generated",
            data=results if data["is_bulk"] else results[0],
        )


class CompleteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CompleteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        object_key = serializer.validated_data["object_key"]
        user = request.user

        try:
            payload = services.read_upload_token(serializer.validated_data["upload_token"])
        except signing.SignatureExpired:
            return error_response("This upload has expired. Request a new upload URL.", status_code=400)
        except signing.BadSignature:
            return error_response("Invalid upload token", status_code=400)

        # The token must belong to this user, this organization and this exact key
        if (
            payload["u"] != str(user.id)
            or payload["o"] != str(user.organization_id)
            or payload["k"] != object_key
        ):
            return error_response("Invalid upload token", status_code=400)

        # A repeated completion returns the same record
        existing = FileAsset.objects.filter(object_key=object_key).first()
        if existing:
            if existing.organization_id != user.organization_id or existing.deleted_at:
                return error_response("This upload is no longer available", status_code=400)
            return success_response(message="Upload already completed", data=FileAssetSerializer(existing).data)

        # Permissions can change between presign and complete, so check again
        policy = REGISTRY[payload["t"]]
        parent = policy.get_parent(user, payload["e"])
        if parent is None or not policy.can_upload(user, parent, payload["c"]):
            return error_response("You can no longer attach files here", status_code=403)

        head = s3.head_object(object_key)
        if head is None:
            return error_response("The file was not uploaded", status_code=400)

        if head["ContentLength"] != payload["s"] or head.get("ContentType") != payload["m"]:
            s3.delete_object(object_key)
            return error_response("The uploaded file does not match the declared size or type", status_code=400)

        if not matches_signature(payload["x"], s3.read_head_bytes(object_key)):
            s3.delete_object(object_key)
            return error_response("The file content does not match its type", status_code=400)

        try:
            with transaction.atomic():
                asset = FileAsset.objects.create(
                    organization_id=user.organization_id,
                    uploaded_by=user,
                    object_key=object_key,
                    original_filename=payload["f"],
                    content_type=payload["m"],
                    size_bytes=head["ContentLength"],
                    category=payload["c"],
                    **{policy.fk_field: parent},
                )
        except IntegrityError:
            # Two completions raced each other. The other one won, so return its record.
            asset = FileAsset.objects.filter(object_key=object_key).first()
            if asset is None:
                raise

        return success_response(message="Upload completed", data=FileAssetSerializer(asset).data, status_code=201)
    

def _live_files():
    """Files that exist and have not been rejected by a scan."""
    return FileAsset.objects.active().exclude(scan_status=FileAsset.ScanStatus.REJECTED)


class FileListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = FileListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        user = request.user

        files = _live_files()
        if params.get("entity_type"):
            # Files of one record, shown under that record's own visibility rules.
            # This is how a vendor lists the attachments of an RFQ it was invited to.
            policy = REGISTRY[params["entity_type"]]
            parent = policy.get_parent(user, params["entity_id"])
            if parent is None:
                return error_response("Not found", status_code=404)
            files = policy.visible_assets(user, parent, files.filter(**{policy.fk_field: parent}))
        elif not user.is_superuser:
            files = files.filter(organization_id=user.organization_id)   # only files my company owns

        if params.get("category"):
            files = files.filter(category=params["category"])

        paginator = StandardPagination()
        page = paginator.paginate_queryset(files, request)
        return success_response(
            message="Files fetched",
            data=FileAssetSerializer(page, many=True).data,
            **paginator.get_pagination_meta(),
        )


class FileDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, file_id):
        asset = _live_files().filter(id=file_id).first()
        # 404 for files the user may not see, so the existence of a file is never revealed
        if asset is None or not REGISTRY[asset.entity_type].can_view(request.user, asset):
            return error_response("Not found", status_code=404)

        url = s3.presign_get(asset.object_key, asset.original_filename, asset.content_type)
        logger.info("file download user=%s file=%s", request.user.id, asset.id)   # never log the URL itself
        return success_response(
            message="Download URL generated",
            data={
                "download_url": url,
                "expires_in": settings.DOWNLOAD_URL_EXPIRY_SECONDS,
                "filename": asset.original_filename,
                "content_type": asset.content_type,
                "size_bytes": asset.size_bytes,
            },
        )


class FileDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, file_id):
        asset = FileAsset.objects.active().filter(id=file_id).first()
        if asset is None:
            return error_response("Not found", status_code=404)

        policy = REGISTRY[asset.entity_type]
        if not policy.can_view(request.user, asset):
            return error_response("Not found", status_code=404)
        if not policy.can_delete(request.user, asset):
            return error_response("You cannot delete this file", status_code=403)

        # Hide it in the database first. The S3 object is removed only after the commit.
        # If S3 fails, the file is already hidden and the cleanup command retries the removal.
        services.delete_file_asset(asset)

        logger.info("file deleted user=%s file=%s", request.user.id, asset.id)
        return success_response(message="File deleted", data=None)