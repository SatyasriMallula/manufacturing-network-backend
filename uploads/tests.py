from unittest.mock import patch

from django.contrib.auth.models import Group
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from components.models import Component, ComponentDocument, ComponentDocumentAccess
from organizations.models import Organization, OrganizationComplianceInfo
from rfqs.models import RFQ, RFQRecipient
from users.models import User

from .models import FileAsset

PRESIGN = "/api/v1/uploads/presign/"
COMPLETE = "/api/v1/uploads/complete/"
LIST = "/api/v1/uploads/"
JPEG_HEAD = b"\xff\xd8\xff\xe0" + b"\x00" * 12


def make_org(name, verified=False):
    org = Organization.objects.create(name=name)
    if verified:
        OrganizationComplianceInfo.objects.create(organization=org, verification_status="verified")
    return org


def make_user(email, org, *roles):
    user = User.objects.create_user(email=email, password="Test@12345", organization=org)
    for role in roles:
        user.groups.add(Group.objects.get_or_create(name=role)[0])
    return user


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


class UploadTestBase(APITestCase):
    def setUp(self):
        self.org_a = make_org("Org A", verified=True)
        self.org_b = make_org("Org B", verified=True)
        self.admin_a = make_user("a@a.com", self.org_a, "company_admin")
        self.admin_b = make_user("b@b.com", self.org_b, "company_admin")
        self.component = Component.objects.create(organization=self.org_a, name="Bracket", category="CNC")
        self.a = client_for(self.admin_a)
        self.b = client_for(self.admin_b)

    def image_body(self, **overrides):
        body = {
            "entity_type": "component", "entity_id": str(self.component.id), "category": "image",
            "filename": "part.jpg", "content_type": "image/jpeg", "size_bytes": 1000,
        }
        body.update(overrides)
        return body

    def presign(self, client=None, **overrides):
        with patch("uploads.s3.presign_put", return_value="https://s3.example/put"):
            return (client or self.a).post(PRESIGN, self.image_body(**overrides), format="json")

    def complete(self, issued, client=None, head=None, head_bytes=JPEG_HEAD):
        head = head if head is not None else {"ContentLength": 1000, "ContentType": "image/jpeg"}
        with patch("uploads.s3.head_object", return_value=head), \
             patch("uploads.s3.read_head_bytes", return_value=head_bytes):
            return (client or self.a).post(
                COMPLETE,
                {"object_key": issued["object_key"], "upload_token": issued["upload_token"]},
                format="json",
            )


class PresignTests(UploadTestBase):
    def test_single_file_success(self):
        res = self.presign()
        self.assertEqual(res.status_code, 200)
        data = res.data["data"]
        self.assertEqual(data["method"], "PUT")
        self.assertEqual(data["headers"], {"Content-Type": "image/jpeg"})
        self.assertTrue(data["object_key"].startswith(f"organizations/{self.org_a.id}/components/{self.component.id}/"))
        self.assertNotIn("part", data["object_key"])   # the original filename never decides the key

    def test_bulk_returns_a_list(self):
        files = [{"filename": f"p{i}.jpg", "content_type": "image/jpeg", "size_bytes": 500} for i in range(3)]
        with patch("uploads.s3.presign_put", return_value="https://s3.example/put"):
            res = self.a.post(PRESIGN, {
                "entity_type": "component", "entity_id": str(self.component.id),
                "category": "image", "files": files,
            }, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data["data"]), 3)

    def test_bulk_over_the_limit_is_rejected(self):
        files = [{"filename": f"p{i}.jpg", "content_type": "image/jpeg", "size_bytes": 500} for i in range(11)]
        res = self.a.post(PRESIGN, {
            "entity_type": "component", "entity_id": str(self.component.id),
            "category": "image", "files": files,
        }, format="json")
        self.assertEqual(res.status_code, 400)

    def test_unsupported_extension(self):
        self.assertEqual(self.presign(filename="virus.exe", content_type="application/octet-stream").status_code, 400)

    def test_mismatched_mime_type(self):
        self.assertEqual(self.presign(content_type="application/pdf").status_code, 400)

    def test_oversized_file(self):
        self.assertEqual(self.presign(size_bytes=20 * 1024 * 1024).status_code, 400)

    def test_unauthenticated(self):
        res = APIClient().post(PRESIGN, self.image_body(), format="json")
        self.assertIn(res.status_code, (401, 403))

    def test_other_organizations_component_is_not_found(self):
        self.assertEqual(self.presign(client=self.b).status_code, 404)   # a draft component of Org A


class CompleteTests(UploadTestBase):
    def test_success_creates_the_record(self):
        issued = self.presign().data["data"]
        res = self.complete(issued)
        self.assertEqual(res.status_code, 201)
        asset = FileAsset.objects.get(object_key=issued["object_key"])
        self.assertEqual(asset.organization_id, self.org_a.id)
        self.assertEqual(asset.component_id, self.component.id)

    def test_object_missing_in_s3(self):
        issued = self.presign().data["data"]
        with patch("uploads.s3.head_object", return_value=None):
            res = self.a.post(COMPLETE, {"object_key": issued["object_key"], "upload_token": issued["upload_token"]}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertFalse(FileAsset.objects.exists())

    def test_size_mismatch_deletes_the_object(self):
        issued = self.presign().data["data"]
        with patch("uploads.s3.delete_object") as deleted:
            res = self.complete(issued, head={"ContentLength": 999999, "ContentType": "image/jpeg"})
        self.assertEqual(res.status_code, 400)
        deleted.assert_called_once()

    def test_spoofed_content_is_rejected(self):
        issued = self.presign().data["data"]
        with patch("uploads.s3.delete_object") as deleted:
            res = self.complete(issued, head_bytes=b"MZ" + b"\x00" * 14)   # an executable pretending to be a jpg
        self.assertEqual(res.status_code, 400)
        deleted.assert_called_once()

    def test_duplicate_completion_returns_the_same_record(self):
        issued = self.presign().data["data"]
        first = self.complete(issued)
        second = self.complete(issued)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["data"]["id"], second.data["data"]["id"])
        self.assertEqual(FileAsset.objects.count(), 1)

    def test_another_users_token_is_rejected(self):
        issued = self.presign().data["data"]
        self.assertEqual(self.complete(issued, client=self.b).status_code, 400)

    def test_expired_token(self):
        issued = self.presign().data["data"]
        with override_settings(UPLOAD_URL_EXPIRY_SECONDS=-1000):
            res = self.complete(issued)
        self.assertEqual(res.status_code, 400)


class AccessTests(UploadTestBase):
    def make_asset(self, **extra):
        defaults = dict(
            organization=self.org_a, uploaded_by=self.admin_a, object_key=f"organizations/x/{FileAsset.objects.count()}.jpg",
            original_filename="part.jpg", content_type="image/jpeg", size_bytes=10,
            category="image", component=self.component,
        )
        defaults.update(extra)
        return FileAsset.objects.create(**defaults)

    def test_list_shows_only_my_organizations_files(self):
        self.make_asset()
        self.assertEqual(len(self.a.get(LIST).data["data"]), 1)
        self.assertEqual(len(self.b.get(LIST).data["data"]), 0)

    def test_owner_can_download(self):
        asset = self.make_asset()
        with patch("uploads.s3.presign_get", return_value="https://s3.example/get"):
            res = self.a.get(f"{LIST}{asset.id}/download/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["data"]["download_url"], "https://s3.example/get")

    def test_other_organization_cannot_download(self):
        asset = self.make_asset()
        with patch("uploads.s3.presign_get", return_value="https://s3.example/get"):
            self.assertEqual(self.b.get(f"{LIST}{asset.id}/download/").status_code, 404)

    def test_buyer_sees_images_of_an_active_verified_component_but_not_drawings(self):
        self.component.status = "active"
        self.component.save()
        photo = self.make_asset()
        drawing = self.make_asset(category="drawing", original_filename="d.pdf", content_type="application/pdf")
        with patch("uploads.s3.presign_get", return_value="https://s3.example/get"):
            self.assertEqual(self.b.get(f"{LIST}{photo.id}/download/").status_code, 200)
            self.assertEqual(self.b.get(f"{LIST}{drawing.id}/download/").status_code, 404)

    def test_invited_vendor_can_download_the_buyers_rfq_attachment(self):
        rfq = RFQ.objects.create(
            buyer_organization=self.org_a, created_by=self.admin_a, title="Need parts", quantity=5, status="open",
        )
        RFQRecipient.objects.create(rfq=rfq, vendor_organization=self.org_b)
        attachment = self.make_asset(
            component=None, rfq=rfq, category="rfq_attachment",
            original_filename="d.pdf", content_type="application/pdf",
        )
        outsider = client_for(make_user("c@c.com", make_org("Org C", verified=True), "company_admin"))
        with patch("uploads.s3.presign_get", return_value="https://s3.example/get"):
            self.assertEqual(self.b.get(f"{LIST}{attachment.id}/download/").status_code, 200)
            self.assertEqual(outsider.get(f"{LIST}{attachment.id}/download/").status_code, 404)


class DeleteTests(AccessTests):
    def test_owner_deletes_and_s3_object_is_removed(self):
        asset = self.make_asset()
        with patch("uploads.s3.delete_object") as deleted, self.captureOnCommitCallbacks(execute=True):
            res = self.a.delete(f"{LIST}{asset.id}/")
        self.assertEqual(res.status_code, 200)
        deleted.assert_called_once_with(asset.object_key)
        asset.refresh_from_db()
        self.assertIsNotNone(asset.deleted_at)
        self.assertIsNotNone(asset.s3_deleted_at)
        self.assertEqual(len(self.a.get(LIST).data["data"]), 0)

    def test_s3_failure_still_hides_the_file_and_can_be_retried(self):
        asset = self.make_asset()
        with patch("uploads.s3.delete_object", side_effect=Exception("S3 down")), self.captureOnCommitCallbacks(execute=True):
            res = self.a.delete(f"{LIST}{asset.id}/")
        self.assertEqual(res.status_code, 200)
        asset.refresh_from_db()
        self.assertIsNotNone(asset.deleted_at)
        self.assertIsNone(asset.s3_deleted_at)   # still waiting for the cleanup command

    def test_other_organization_cannot_delete(self):
        asset = self.make_asset()
        self.assertEqual(self.b.delete(f"{LIST}{asset.id}/").status_code, 404)
        asset.refresh_from_db()
        self.assertIsNone(asset.deleted_at)


class DocumentGrantTests(UploadTestBase):
    def setUp(self):
        super().setUp()
        self.drawing = FileAsset.objects.create(
            organization=self.org_a, uploaded_by=self.admin_a, object_key="organizations/x/drawing.pdf",
            original_filename="d.pdf", content_type="application/pdf", size_bytes=10,
            category="drawing", component=self.component,
        )
        self.doc = ComponentDocument.objects.create(
            component=self.component, uploaded_by=self.admin_a, file_asset=self.drawing,
            doc_type="drawing",
        )

    def grant(self, **extra):
        return ComponentDocumentAccess.objects.create(
            document=self.doc, granted_to_organization=self.org_b, granted_by=self.admin_a, **extra
        )

    def download_status(self, client):
        with patch("uploads.s3.presign_get", return_value="https://s3.example/get"):
            return client.get(f"{LIST}{self.drawing.id}/download/").status_code

    def test_buyer_without_a_grant_cannot_download(self):
        self.assertEqual(self.download_status(self.b), 404)

    def test_buyer_with_a_grant_can_download(self):
        self.grant()
        self.assertEqual(self.download_status(self.b), 200)

    def test_revoked_grant_stops_the_download(self):
        self.grant(is_revoked=True)
        self.assertEqual(self.download_status(self.b), 404)

    def test_rejected_grant_stops_the_download(self):
        self.grant(decision="rejected")
        self.assertEqual(self.download_status(self.b), 404)

    def test_deleting_the_file_removes_the_document_record(self):
        with patch("uploads.s3.delete_object"), self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.a.delete(f"{LIST}{self.drawing.id}/").status_code, 200)
        self.assertFalse(ComponentDocument.objects.filter(id=self.doc.id).exists())