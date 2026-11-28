from django.urls import path
from .views import (
    PresignView, CompleteView, FileListView, FileDownloadView, FileDeleteView,
)

urlpatterns = [
    path("uploads/presign/", PresignView.as_view(), name="upload-presign"),
    path("uploads/complete/", CompleteView.as_view(), name="upload-complete"),
    path("uploads/", FileListView.as_view(), name="upload-list"),
    path("uploads/<uuid:file_id>/", FileDeleteView.as_view(), name="upload-delete"),
    path("uploads/<uuid:file_id>/download/", FileDownloadView.as_view(), name="upload-download"),
]