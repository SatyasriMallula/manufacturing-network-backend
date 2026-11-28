import os
import re

from django.conf import settings
from rest_framework.exceptions import ValidationError

MB = 1024 * 1024

IMAGE_TYPES = {
    "jpg": {"image/jpeg"}, "jpeg": {"image/jpeg"},
    "png": {"image/png"}, "webp": {"image/webp"},
}
DOCUMENT_TYPES = {
    "pdf": {"application/pdf"},
    "docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    "xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
}
# Browsers send CAD files as a generic type or nothing, so the server decides what is signed
CAD_EXTENSIONS = {"step", "stp", "iges", "igs", "dxf", "dwg", "stl"}
CAD_CONTENT_TYPE = "application/octet-stream"

CATEGORY_GROUPS = {
    "image": {"image"},
    "drawing": {"document", "cad", "image"},
    "specification": {"document", "image"},
    "rfq_attachment": {"document", "cad", "image"},
    "quotation": {"document"},
    "purchase_order": {"document"},
    "invoice": {"document"},
    "other": {"document", "image"},
}


def clean_filename(name):
    name = os.path.basename((name or "").replace("\\", "/")).strip()
    return re.sub(r"[\x00-\x1f\x7f]", "", name)[:255]


def group_for_extension(ext):
    if ext in IMAGE_TYPES:
        return "image"
    if ext in DOCUMENT_TYPES:
        return "document"
    if ext in CAD_EXTENSIONS:
        return "cad"
    return None


def validate_file(category, filename, content_type, size_bytes):
    name = clean_filename(filename)
    ext = os.path.splitext(name)[1].lower().lstrip(".")
    if not ext:
        raise ValidationError("The file must have an extension.")

    group = group_for_extension(ext)
    if group is None:
        raise ValidationError(f"Files of type .{ext} are not allowed.")
    if group not in CATEGORY_GROUPS[category]:
        raise ValidationError(f"A .{ext} file cannot be used as {category}.")

    content_type = (content_type or "").split(";")[0].strip().lower()
    if group == "cad":
        content_type = CAD_CONTENT_TYPE
    else:
        allowed = (IMAGE_TYPES if group == "image" else DOCUMENT_TYPES)[ext]
        if content_type not in allowed:
            raise ValidationError(f"Content type '{content_type}' does not match a .{ext} file.")

    limit = settings.UPLOAD_MAX_BYTES[group]
    if size_bytes > limit:
        raise ValidationError(f"File too large. The maximum for this type is {limit // MB} MB.")

    return {"filename": name, "ext": ext, "content_type": content_type, "size_bytes": size_bytes}


def matches_signature(ext, head):
    """Check the real first bytes, which defends against a spoofed Content-Type."""
    if ext == "pdf":
        return head.startswith(b"%PDF-")
    if ext == "png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if ext in ("jpg", "jpeg"):
        return head.startswith(b"\xff\xd8\xff")
    if ext == "webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if ext in ("docx", "xlsx"):
        return head.startswith(b"PK\x03\x04")
    return True   # CAD formats have no reliable signature