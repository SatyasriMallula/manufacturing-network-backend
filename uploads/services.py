import uuid

from django.conf import settings
from django.core import signing

SALT = "uploads.upload-token"

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)


from django.db import transaction


def delete_file_asset(asset):
    """Soft-delete a file, remove the records wrapping it, and delete the S3 object after commit."""
    from components.models import ComponentDocument, ComponentImage
    from rfqs.models import RFQAttachment

    with transaction.atomic():
        asset.deleted_at = timezone.now()
        asset.save(update_fields=["deleted_at", "updated_at"])
        ComponentImage.objects.filter(file_asset=asset).delete()
        ComponentDocument.objects.filter(file_asset=asset).delete()   # also removes its access grants
        RFQAttachment.objects.filter(file_asset=asset).delete()
        transaction.on_commit(lambda: purge_from_s3(asset.pk))

def purge_from_s3(asset_id):
    """Delete the S3 object of a soft-deleted file. Safe to call again: a failure is logged and retried later."""
    from . import s3
    from .models import FileAsset

    asset = FileAsset.objects.filter(pk=asset_id).first()
    if asset is None or asset.s3_deleted_at is not None:
        return True
    try:
        s3.delete_object(asset.object_key)
    except Exception:
        logger.exception("S3 delete failed for file %s. The cleanup command will retry.", asset_id)
        return False
    FileAsset.objects.filter(pk=asset_id).update(s3_deleted_at=timezone.now())
    return True

def build_object_key(owner_org_id, folder, entity_id, ext):
    # The original filename never decides the key
    return f"organizations/{owner_org_id}/{folder}/{entity_id}/{uuid.uuid4().hex}.{ext}"


def issue_upload_token(user, key, entity_type, entity_id, category, file_info):
    """Binds a presigned upload to one user, one parent and one exact file, so complete() trusts none of the client's metadata."""
    return signing.dumps(
        {
            "k": key, "u": str(user.id), "o": str(user.organization_id),
            "t": entity_type, "e": str(entity_id), "c": category,
            "f": file_info["filename"], "m": file_info["content_type"], "s": file_info["size_bytes"],
            "x": file_info["ext"],
        },
        salt=SALT,
    )


def read_upload_token(token):
    return signing.loads(token, salt=SALT, max_age=settings.UPLOAD_URL_EXPIRY_SECONDS + 600)