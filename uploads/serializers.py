from django.conf import settings
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from .models import FileAsset
from .policies import REGISTRY
from .validators import validate_file


class FileSpecSerializer(serializers.Serializer):
    filename = serializers.CharField(max_length=255)
    content_type = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    size_bytes = serializers.IntegerField(min_value=1)


class PresignRequestSerializer(serializers.Serializer):
    entity_type = serializers.ChoiceField(choices=list(REGISTRY))
    entity_id = serializers.UUIDField()
    category = serializers.ChoiceField(choices=FileAsset.Category.choices)

    # Single file: send these three directly. Bulk: send a files list instead.
    filename = serializers.CharField(max_length=255, required=False)
    content_type = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    size_bytes = serializers.IntegerField(min_value=1, required=False)
    files = FileSpecSerializer(many=True, required=False, allow_empty=False)

    def validate(self, attrs):
        has_single = "filename" in attrs or "size_bytes" in attrs
        files = attrs.get("files")
        if has_single and files:
            raise ValidationError("Send either one file or a files list, not both.")
        if not has_single and not files:
            raise ValidationError("Send a file (filename, content_type, size_bytes) or a files list.")

        is_bulk = bool(files)
        if not is_bulk:
            if "filename" not in attrs or "size_bytes" not in attrs:
                raise ValidationError("filename and size_bytes are required.")
            files = [{"filename": attrs["filename"], "content_type": attrs.get("content_type", ""), "size_bytes": attrs["size_bytes"]}]

        if len(files) > settings.UPLOAD_MAX_FILES_PER_REQUEST:
            raise ValidationError({"files": f"At most {settings.UPLOAD_MAX_FILES_PER_REQUEST} files per request."})

        validated, errors = [], {}
        for index, spec in enumerate(files):
            try:
                validated.append(
                    validate_file(attrs["category"], spec["filename"], spec.get("content_type", ""), spec["size_bytes"])
                )
            except ValidationError as exc:
                errors[str(index)] = exc.detail
        if errors:
            raise ValidationError({"files": errors})

        return {
            "entity_type": attrs["entity_type"], "entity_id": attrs["entity_id"],
            "category": attrs["category"], "files": validated, "is_bulk": is_bulk,
        }


class CompleteRequestSerializer(serializers.Serializer):
    object_key = serializers.CharField(max_length=500)
    upload_token = serializers.CharField()


class FileAssetSerializer(serializers.ModelSerializer):
    entity_type = serializers.CharField(read_only=True)
    entity_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = FileAsset
        fields = [
            "id", "category", "original_filename", "content_type", "size_bytes",
            "entity_type", "entity_id", "uploaded_by", "created_at",
        ]

class FileListQuerySerializer(serializers.Serializer):
    entity_type = serializers.ChoiceField(choices=list(REGISTRY), required=False)
    entity_id = serializers.UUIDField(required=False)
    category = serializers.ChoiceField(choices=FileAsset.Category.choices, required=False)

    def validate(self, attrs):
        if ("entity_type" in attrs) != ("entity_id" in attrs):
            raise ValidationError("Send entity_type and entity_id together.")
        return attrs
