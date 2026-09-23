import json
import re
from bisect import bisect_left
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from game.models import Card, Rarity

TEXT_BLOCKS = {"title", "text", "textImage"}
PLACEHOLDER_IMAGE = "/home/komi_banner.png"  # Komi's default picture for pages without one
HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")

# Minimum share of cards with strictly fewer subscribers needed for each rarity, best first.
# Rank-based because subscriber counts are extremely skewed (median 1, max 769).
RARITY_THRESHOLDS = [
    (0.99, Rarity.LEGENDARY),
    (0.95, Rarity.EPIC),
    (0.85, Rarity.RARE),
    (0.60, Rarity.UNCOMMON),
]


def blocks_to_text(blocks):
    """Plain text of a page's presentation blocks, in display order."""
    parts = []
    for block in sorted(blocks or [], key=lambda b: b.get("position", 0)):
        if block.get("type") not in TEXT_BLOCKS:
            continue
        text = (block.get("bloc_data") or {}).get("text")
        if isinstance(text, list):  # Quill delta: [{"insert": "..."}, ...]
            text = "".join(op["insert"] for op in text if isinstance(op.get("insert"), str))
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())
    return "\n\n".join(parts)


def local_image(record, url):
    """Downloaded copy of `url`, relative to MEDIA_ROOT (images/), or "" if there is none."""
    if not url or PLACEHOLDER_IMAGE in url:
        return ""
    return (record.get("_local_images") or {}).get(url, "").removeprefix("images/")


def color(value):
    # Colors end up in an inline style attribute: only accept a strict #rrggbb.
    return value if isinstance(value, str) and HEX_COLOR.fullmatch(value) else ""


def card_fields(record):
    meta = record.get("metadata") or {}  # null for most members (403 when scraping)
    page = meta.get("page") or {}
    return {
        "name": (record.get("name") or "").strip()[:200] or "???",
        "tagline": (record.get("description") or "").strip()[:500],
        "description": blocks_to_text(record.get("blocks")),
        "logo": local_image(record, record.get("logo_url")),
        "banner": local_image(record, record.get("banner_url")),
        "primary_color": color(page.get("primary_color")),
        "secondary_color": color(page.get("secondary_color")),
        "subscriber_count": meta.get("subscriber_count", record.get("subscriber_count")) or 0,
        "post_count": meta.get("post_count") or 0,
        "event_count": meta.get("event_count") or 0,
    }


def rarity_for(count, sorted_counts):
    share = bisect_left(sorted_counts, count) / len(sorted_counts)
    return next((rarity for minimum, rarity in RARITY_THRESHOLDS if share >= minimum), Rarity.COMMON)


def assign_rarities():
    cards = list(Card.objects.only("id", "subscriber_count"))
    counts = sorted(card.subscriber_count for card in cards)
    for card in cards:
        card.rarity = rarity_for(card.subscriber_count, counts)
    Card.objects.bulk_update(cards, ["rarity"], batch_size=500)


class Command(BaseCommand):
    help = "Import a komi_pages_dump.json as cards, then rank rarities by subscriber_count."

    def add_arguments(self, parser):
        parser.add_argument("dump", type=Path)

    @transaction.atomic
    def handle(self, dump, **options):
        data = json.loads(dump.read_text(encoding="utf-8"))
        records = data.get("clubs", []) + data.get("members", [])
        for record in records:
            Card.objects.update_or_create(komi_id=record["id"], defaults=card_fields(record))
        assign_rarities()
        tally = {r.label: Card.objects.filter(rarity=r).count() for r in Rarity}
        self.stdout.write(self.style.SUCCESS(f"Imported {len(records)} cards. Rarities: {tally}"))
