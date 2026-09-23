import json
import tempfile
import uuid
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from game.management.commands.import_komi import (
    assign_rarities,
    blocks_to_text,
    card_fields,
    color,
    local_image,
    rarity_for,
)
from game.models import Card, Pull, Rarity, User

CLUB = {
    "id": "3ce8b812-6527-4668-8e86-5c3709de280a",
    "name": "BDE",
    "type": "page",
    "description": "Cercle des élèves ⭕️",
    "subscriber_count": 473,
    "logo_url": "https://cdn.example/x/logo.webp",
    "banner_url": "https://cdn.example/home/komi_banner.png",
    "_local_images": {
        "https://cdn.example/x/logo.webp": "images/3ce8b812-6527-4668-8e86-5c3709de280a/logo.webp"
    },
    "metadata": {
        "subscriber_count": 473,
        "post_count": 12,
        "event_count": 3,
        "page": {"primary_color": "#b80c09", "secondary_color": "#6a040f"},
    },
    "blocks": [
        {"type": "text", "position": 1, "bloc_data": {"text": [
            {"insert": "Hello "}, {"insert": "world", "attributes": {"bold": True}}]}},
        {"type": "title", "position": 0, "bloc_data": {"text": [{"insert": "Le Bureau\n"}]}},
        {"type": "button", "position": 2, "bloc_data": {"name": "Insta", "data": "https://x"}},
        {"type": "textImage", "position": 3, "bloc_data": {"text": "**Sport** first", "format": "markdown"}},
    ],
}

MEMBER = {
    "id": "31aa01a7-c874-4a4c-97ab-e2a839656b12",
    "name": "Alex Martin",
    "type": "user",
    "user_id": "40e010f4-4b93-4b7c-a86c-eae61ae8bad2",
    "description": "alex_m",
    "subscriber_count": 2,
    "logo_url": "https://cdn.example/home/komi_banner.png",
    "banner_url": "https://cdn.example/home/komi_banner.png",
    "_local_images": {},
    "metadata": None,
    "blocks": None,
}


def write_dump(data):
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(data, f)
    f.close()
    return Path(f.name)


class HelperTests(TestCase):
    def test_blocks_to_text_orders_by_position_and_skips_non_text(self):
        self.assertEqual(
            blocks_to_text(CLUB["blocks"]), "Le Bureau\n\nHello world\n\n**Sport** first"
        )

    def test_blocks_to_text_handles_missing_blocks(self):
        self.assertEqual(blocks_to_text(None), "")
        self.assertEqual(blocks_to_text([]), "")

    def test_local_image_strips_images_prefix(self):
        self.assertEqual(
            local_image(CLUB, CLUB["logo_url"]),
            "3ce8b812-6527-4668-8e86-5c3709de280a/logo.webp",
        )

    def test_local_image_ignores_placeholder_and_unknown_urls(self):
        self.assertEqual(local_image(CLUB, CLUB["banner_url"]), "")
        self.assertEqual(local_image(CLUB, "https://cdn.example/not-downloaded.png"), "")
        self.assertEqual(local_image(CLUB, None), "")

    def test_color_rejects_non_hex(self):
        self.assertEqual(color("#b80c09"), "#b80c09")
        self.assertEqual(color("red;background:url(x)"), "")
        self.assertEqual(color("ff02b2fd"), "")
        self.assertEqual(color(None), "")

    def test_member_without_metadata(self):
        fields = card_fields(MEMBER)
        self.assertEqual(fields["subscriber_count"], 2)  # falls back to the top-level value
        self.assertEqual(fields["post_count"], 0)
        self.assertEqual(fields["description"], "")
        self.assertEqual(fields["logo"], "")
        self.assertEqual(fields["primary_color"], "")
        self.assertEqual(fields["tagline"], "alex_m")

    def test_empty_name_gets_placeholder(self):
        self.assertEqual(card_fields({**MEMBER, "name": "  "})["name"], "???")

    def test_rarity_for_uses_rank_share(self):
        counts = sorted([0] * 60 + [1] * 25 + [5] * 10 + [50] * 4 + [500])
        self.assertEqual(rarity_for(0, counts), Rarity.COMMON)
        self.assertEqual(rarity_for(1, counts), Rarity.UNCOMMON)
        self.assertEqual(rarity_for(5, counts), Rarity.RARE)
        self.assertEqual(rarity_for(50, counts), Rarity.EPIC)
        self.assertEqual(rarity_for(500, counts), Rarity.LEGENDARY)

    def test_rarity_for_single_card_is_common(self):
        self.assertEqual(rarity_for(769, [769]), Rarity.COMMON)

    def test_assign_rarities_ranks_every_card_in_db(self):
        counts = [0] * 60 + [1] * 25 + [5] * 10 + [50] * 4 + [500]
        Card.objects.bulk_create(
            Card(komi_id=uuid.uuid4(), name=str(i), subscriber_count=c) for i, c in enumerate(counts)
        )
        assign_rarities()
        self.assertEqual(Card.objects.get(subscriber_count=500).rarity, Rarity.LEGENDARY)
        self.assertEqual(Card.objects.filter(rarity=Rarity.COMMON).count(), 60)
        self.assertEqual(Card.objects.filter(rarity=Rarity.EPIC).count(), 4)


class CommandTests(TestCase):
    def call_import(self, data):
        path = write_dump(data)
        self.addCleanup(path.unlink)
        call_command("import_komi", path, stdout=StringIO())

    def test_imports_clubs_and_members(self):
        self.call_import({"clubs": [CLUB], "members": [MEMBER]})
        self.assertEqual(Card.objects.count(), 2)
        bde = Card.objects.get(komi_id=CLUB["id"])
        self.assertEqual(bde.name, "BDE")
        self.assertEqual(bde.tagline, "Cercle des élèves ⭕️")
        self.assertEqual(bde.logo.name, "3ce8b812-6527-4668-8e86-5c3709de280a/logo.webp")
        self.assertEqual(bde.banner.name, "")
        self.assertEqual((bde.subscriber_count, bde.post_count, bde.event_count), (473, 12, 3))
        self.assertEqual(bde.primary_color, "#b80c09")

    def test_reimport_updates_in_place(self):
        self.call_import({"clubs": [CLUB], "members": [MEMBER]})
        bde = Card.objects.get(komi_id=CLUB["id"])
        user = User.objects.create_user("ash", password="pw")
        Pull.objects.create(user=user, card=bde, opened_at="2026-09-23T10:00:00Z")

        self.call_import({"clubs": [{**CLUB, "name": "BDE 2027"}], "members": [MEMBER]})

        self.assertEqual(Card.objects.count(), 2)
        self.assertEqual(Pull.objects.get().card.name, "BDE 2027")
