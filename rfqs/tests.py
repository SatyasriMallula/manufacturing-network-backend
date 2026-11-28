from django.test import TestCase
from django.contrib.auth.models import Group
from rest_framework.test import APIClient
from unittest.mock import patch

from organizations.models import Organization, OrganizationComplianceInfo
from users.models import User
from uploads.models import FileAsset

from .models import RFQ, RFQAttachment


class RFQAttachmentUploadTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Buyer")
        OrganizationComplianceInfo.objects.create(
            organization=self.organization,
            verification_status=OrganizationComplianceInfo.VerificationStatus.VERIFIED,
        )
        self.user = User.objects.create_user(
            email="buyer@example.com", password="Test@12345", organization=self.organization,
        )
        self.user.groups.add(Group.objects.get_or_create(name="company_admin")[0])
        self.rfq = RFQ.objects.create(
            buyer_organization=self.organization, created_by=self.user,
            title="Bracket", quantity=1, status=RFQ.Status.DRAFT,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = f"/api/v1/rfqs/{self.rfq.id}/attachments/"

    def make_asset(self, rfq=None, **overrides):
        values = {
            "organization": self.organization,
            "uploaded_by": self.user,
            "object_key": f"organizations/{self.organization.id}/rfqs/{self.rfq.id}/drawing.pdf",
            "original_filename": "drawing.pdf",
            "content_type": "application/pdf",
            "size_bytes": 100,
            "category": FileAsset.Category.RFQ_ATTACHMENT,
            "rfq": rfq or self.rfq,
        }
        values.update(overrides)
        return FileAsset.objects.create(**values)

    def test_completed_s3_asset_can_be_attached_once(self):
        asset = self.make_asset()
        response = self.client.post(
            self.url, {"file_asset_id": str(asset.id), "title": "Design drawing"}, format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["file_asset_id"], str(asset.id))
        self.assertEqual(response.data["data"]["filename"], "drawing.pdf")
        self.assertEqual(response.data["data"]["size_bytes"], 100)
        self.assertNotIn("file", response.data["data"])
        self.assertEqual(RFQAttachment.objects.get().file_asset_id, asset.id)

        duplicate = self.client.post(
            self.url, {"file_asset_id": str(asset.id)}, format="json",
        )
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(RFQAttachment.objects.count(), 1)

    def test_assets_for_another_rfq_cannot_be_attached(self):
        other_rfq = RFQ.objects.create(
            buyer_organization=self.organization, created_by=self.user,
            title="Other bracket", quantity=1, status=RFQ.Status.DRAFT,
        )
        asset = self.make_asset(rfq=other_rfq, object_key="other/drawing.pdf")

        response = self.client.post(
            self.url, {"file_asset_id": str(asset.id)}, format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(RFQAttachment.objects.exists())

    def test_deleting_attachment_soft_deletes_s3_asset(self):
        asset = self.make_asset()
        attachment = RFQAttachment.objects.create(
            rfq=self.rfq, uploaded_by=self.user, file_asset=asset,
        )

        with patch("uploads.s3.delete_object") as delete_object:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.delete(f"{self.url}{attachment.id}/")

        self.assertEqual(response.status_code, 200)
        asset.refresh_from_db()
        self.assertIsNotNone(asset.deleted_at)
        self.assertFalse(RFQAttachment.objects.filter(pk=attachment.pk).exists())
        delete_object.assert_called_once_with(asset.object_key)
