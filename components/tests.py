from django.test import SimpleTestCase
from django.urls import reverse

from orders.models import Order
from orders.serializers import OrderSerializer
from rfqs.models import RFQRecipient
from rfqs.serializers import RFQRecipientSerializer, RFQVendorInputSerializer

from .models import Component, ComponentDocument, ComponentImage


class ComponentRenameTests(SimpleTestCase):
    def test_component_models_use_requested_tables_and_relationships(self):
        self.assertEqual(Component._meta.app_label, "components")
        self.assertEqual(Component._meta.db_table, "components")
        self.assertEqual(ComponentImage._meta.db_table, "component_images")
        self.assertEqual(ComponentDocument._meta.db_table, "component_documents")
        self.assertEqual(ComponentImage._meta.get_field("component").remote_field.related_name, "images")
        self.assertEqual(ComponentDocument._meta.get_field("component").remote_field.related_name, "documents")

    def test_rfq_and_order_contracts_use_component_fields(self):
        self.assertIn("component", [field.name for field in RFQRecipient._meta.get_fields()])
        self.assertEqual(
            set(RFQRecipientSerializer().fields) & {"component", "component_name", "product", "product_name"},
            {"component", "component_name"},
        )
        self.assertEqual(
            set(OrderSerializer().fields) & {"component", "component_name", "product", "product_name"},
            {"component", "component_name"},
        )
        self.assertIn("component", RFQVendorInputSerializer().fields)

    def test_component_endpoints_resolve_under_new_prefix(self):
        component_id = "00000000-0000-0000-0000-000000000001"
        image_id = "00000000-0000-0000-0000-000000000002"
        document_id = "00000000-0000-0000-0000-000000000003"

        self.assertEqual(reverse("component-list"), "/api/v1/components/")
        self.assertEqual(reverse("my-components"), "/api/v1/components/my/")
        self.assertEqual(
            reverse("my-component-detail", kwargs={"component_id": component_id}),
            f"/api/v1/components/my/{component_id}/",
        )
        self.assertEqual(
            reverse("component-images", kwargs={"component_id": component_id}),
            f"/api/v1/components/{component_id}/images/",
        )
        self.assertEqual(
            reverse("component-image-delete", kwargs={"component_id": component_id, "image_id": image_id}),
            f"/api/v1/components/{component_id}/images/{image_id}/",
        )
        self.assertEqual(
            reverse("component-documents", kwargs={"component_id": component_id}),
            f"/api/v1/components/{component_id}/documents/",
        )
        self.assertEqual(
            reverse("component-document-delete", kwargs={"component_id": component_id, "document_id": document_id}),
            f"/api/v1/components/{component_id}/documents/{document_id}/",
        )
        self.assertEqual(
            reverse("component-reviews", kwargs={"component_id": component_id}),
            f"/api/v1/components/{component_id}/reviews/",
        )
