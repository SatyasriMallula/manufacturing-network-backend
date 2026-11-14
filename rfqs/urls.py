from django.urls import path
from .views import RFQAwardView, RFQListCreateView, RFQDetailView, RFQAttachmentCreateView, RFQAttachmentDeleteView,RFQQuoteListView, RFQQuoteView


urlpatterns = [
    path("rfqs/", RFQListCreateView.as_view(), name="rfq-list-create"),
    path("rfqs/<uuid:rfq_id>/", RFQDetailView.as_view(), name="rfq-detail"),
    path("rfqs/<uuid:rfq_id>/attachments/", RFQAttachmentCreateView.as_view(), name="rfq-attachment-create"),
    path("rfqs/<uuid:rfq_id>/attachments/<uuid:attachment_id>/", RFQAttachmentDeleteView.as_view(), name="rfq-attachment-delete"),
    path("rfqs/<uuid:rfq_id>/award/", RFQAwardView.as_view(), name="rfq-award"),
    path("rfqs/<uuid:rfq_id>/quote/", RFQQuoteView.as_view(), name="rfq-quote"),
    path("rfqs/<uuid:rfq_id>/quotes/", RFQQuoteListView.as_view(), name="rfq-quotes"),
]