import logging

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from django.conf import settings

logger = logging.getLogger(__name__)
_client = None


def get_s3_client():
    """Credentials come from the default chain: AWS CLI locally, the IAM role on EC2."""
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            region_name=settings.AWS_S3_REGION_NAME,
            config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
        )
    return _client


def presign_put(key, content_type, size_bytes):
    return get_s3_client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
            "Key": key,
            "ContentType": content_type,
            "ContentLength": size_bytes,   # signed, so S3 rejects an upload of a different size
        },
        ExpiresIn=settings.UPLOAD_URL_EXPIRY_SECONDS,
        HttpMethod="PUT",
    )


def presign_get(key, filename, content_type):
    from urllib.parse import quote

    return get_s3_client().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
            "Key": key,
            # attachment: the browser downloads it and never renders it inside your origin
            "ResponseContentDisposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "ResponseContentType": content_type,
        },
        ExpiresIn=settings.DOWNLOAD_URL_EXPIRY_SECONDS,
        HttpMethod="GET",
    )


def head_object(key):
    """Object metadata, or None if it does not exist."""
    try:
        return get_s3_client().head_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return None
        raise


def read_head_bytes(key, count=16):
    response = get_s3_client().get_object(
        Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=key, Range=f"bytes=0-{count - 1}"
    )
    return response["Body"].read()


def delete_object(key):
    get_s3_client().delete_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=key)