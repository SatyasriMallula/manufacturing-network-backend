from django.contrib import admin
from .models import FileAsset


@admin.register(FileAsset)
class FileAssetAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "category", "organization", "size_bytes", "created_at", "deleted_at")
    list_filter = ("category", "scan_status")
    search_fields = ("original_filename", "object_key")
    readonly_fields = ("object_key",)