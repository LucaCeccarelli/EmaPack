import io
import shutil
import tempfile
import uuid

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from game.management.commands.import_komi import assign_rarities
from game.models import Card, Pull, Rarity, Status, User
from game.packs import PackUnavailable, open_pack
from game.views import MAX_PENDING_PROPOSALS

MEDIA = tempfile.mkdtemp()


def png(name="logo.png", size=(8, 8)):
    buf = io.BytesIO()
    Image.new("RGB", size, "#ff3d77").save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def make_card(status=Status.APPROVED, rarity=Rarity.COMMON, name="card", **kw):
    return Card.objects.create(komi_id=uuid.uuid4() if status == Status.APPROVED else None,
                               name=name, rarity=rarity, status=status, **kw)


def valid_data(**overrides):
    return {"name": "Club Échecs", "tagline": "Check mate", "description": "We play chess.",
            "primary_color": "#112233", "secondary_color": "#445566", **overrides}


@override_settings(MEDIA_ROOT=MEDIA)
class ProposePageTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.user = User.objects.create_user("ash", password="pw")
        self.client.force_login(self.user)
        self.url = reverse("propose_card")

    def test_requires_login(self):
        self.client.logout()
        self.assertRedirects(self.client.get(self.url), f"{reverse('login')}?next={self.url}")

    def test_page_has_editor_and_preview(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'id="card-editor"')
        self.assertContains(response, 'class="card rarity-common"')

    def test_valid_proposal_is_saved_as_pending(self):
        response = self.client.post(self.url, valid_data(logo=png(), banner=png("banner.png", (16, 8))))
        self.assertRedirects(response, self.url)
        card = Card.objects.get(name="Club Échecs")
        self.assertEqual(card.status, Status.PENDING)
        self.assertEqual(card.proposed_by, self.user)
        self.assertIsNotNone(card.proposed_at)
        self.assertIsNone(card.komi_id)
        self.assertTrue(card.logo.name.startswith("proposals/"))
        self.assertEqual((card.primary_color, card.secondary_color), ("#112233", "#445566"))
        self.assertContains(self.client.get(self.url), "Club Échecs")  # listed under "your proposals"

    def test_suggested_rarity_is_saved_for_the_admin(self):
        self.client.post(self.url, valid_data(rarity=Rarity.LEGENDARY))
        self.assertEqual(Card.objects.get().rarity, Rarity.LEGENDARY)

    def test_rarity_defaults_to_common_and_rejects_nonsense(self):
        self.client.post(self.url, valid_data())
        self.assertEqual(Card.objects.get().rarity, Rarity.COMMON)
        response = self.client.post(self.url, valid_data(name="Other", rarity=9))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Card.objects.filter(name="Other").exists())

    def test_images_are_optional(self):
        self.client.post(self.url, valid_data())
        self.assertEqual(Card.objects.get().logo.name, "")

    def test_rejects_bad_colors(self):
        response = self.client.post(self.url, valid_data(primary_color="red;background:url(x)"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Card.objects.exists())

    def test_rejects_files_that_are_not_images(self):
        fake = SimpleUploadedFile("logo.png", b"<script>alert(1)</script>", content_type="image/png")
        response = self.client.post(self.url, valid_data(logo=fake))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Card.objects.exists())

    @override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=None)
    def test_rejects_huge_images(self):
        with self.settings(PROPOSAL_MAX_IMAGE_BYTES=100):
            response = self.client.post(self.url, valid_data(logo=png(size=(64, 64))))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Card.objects.exists())

    def test_length_limits_are_enforced_server_side(self):
        response = self.client.post(self.url, valid_data(name="x" * 41))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Card.objects.exists())
        self.assertContains(self.client.get(self.url), 'maxlength="40"')

    def test_admin_cannot_add_orphan_proposals(self):
        admin = User.objects.create_superuser("boss", password="pw")
        self.client.force_login(admin)
        self.assertEqual(self.client.get(reverse("admin:game_cardproposal_add")).status_code, 403)

    def test_name_is_required(self):
        self.client.post(self.url, valid_data(name=""))
        self.assertFalse(Card.objects.exists())

    def test_limit_on_pending_proposals(self):
        for i in range(MAX_PENDING_PROPOSALS):
            make_card(status=Status.PENDING, name=f"p{i}", proposed_by=self.user)
        self.client.post(self.url, valid_data())
        self.assertEqual(Card.objects.filter(proposed_by=self.user).count(), MAX_PENDING_PROPOSALS)

    def test_only_own_proposals_are_listed(self):
        other = User.objects.create_user("gary", password="pw")
        make_card(status=Status.PENDING, name="Gary's secret card", proposed_by=other)
        self.assertNotContains(self.client.get(self.url), "Gary&#x27;s secret card")


class ProposalLifecycleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ash", password="pw")

    def test_pending_and_rejected_cards_are_never_pulled(self):
        make_card(name="approved")
        make_card(status=Status.PENDING, name="pending", rarity=Rarity.LEGENDARY)
        make_card(status=Status.REJECTED, name="rejected", rarity=Rarity.EPIC)
        cards = open_pack(self.user)
        self.assertEqual({c.name for c in cards}, {"approved"})

    def test_pack_unavailable_when_only_pending_cards(self):
        make_card(status=Status.PENDING)
        with self.assertRaises(PackUnavailable):
            open_pack(self.user)

    def test_admin_approves_with_a_rarity_then_card_can_be_pulled(self):
        admin = User.objects.create_superuser("boss", password="pw")
        self.client.force_login(admin)
        card = make_card(status=Status.PENDING, name="New club", proposed_by=self.user)
        url = reverse("admin:game_cardproposal_changelist")
        self.assertContains(self.client.get(url), "New club")
        self.client.post(url, {"action": "approve", "_selected_action": [card.pk]})
        card.refresh_from_db()
        self.assertEqual(card.status, Status.APPROVED)
        self.assertEqual(open_pack(self.user)[0], card)

    def test_admin_rejects(self):
        admin = User.objects.create_superuser("boss", password="pw")
        self.client.force_login(admin)
        card = make_card(status=Status.PENDING, proposed_by=self.user)
        self.client.post(reverse("admin:game_cardproposal_changelist"),
                         {"action": "reject", "_selected_action": [card.pk]})
        card.refresh_from_db()
        self.assertEqual(card.status, Status.REJECTED)

    def test_collection_total_counts_only_approved_cards(self):
        mine = make_card(name="mine")
        make_card(status=Status.PENDING)
        Pull.objects.create(user=self.user, card=mine, opened_at=timezone.now())
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("collection")), "1 of 1 cards discovered")

    def test_import_ranking_leaves_proposed_cards_alone(self):
        Card.objects.bulk_create(Card(komi_id=uuid.uuid4(), name=str(i), subscriber_count=i) for i in range(100))
        proposed = make_card(status=Status.PENDING, rarity=Rarity.EPIC, proposed_by=self.user)
        assign_rarities()
        proposed.refresh_from_db()
        self.assertEqual(proposed.rarity, Rarity.EPIC)
        self.assertEqual(Card.objects.get(name="99").rarity, Rarity.LEGENDARY)
