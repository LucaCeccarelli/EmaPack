import random
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import Card, Pull, Rarity, User

PACK_SIZE = 5
PACK_COOLDOWN = timedelta(minutes=10)
# Relative odds per slot. The last slot is the "hit": always Rare or better.
SLOT_ODDS = {Rarity.COMMON: 60, Rarity.UNCOMMON: 25, Rarity.RARE: 10, Rarity.EPIC: 4, Rarity.LEGENDARY: 1}
HIT_ODDS = {Rarity.RARE: 75, Rarity.EPIC: 20, Rarity.LEGENDARY: 5}


class PackUnavailable(Exception):
    """The user can't open a pack right now (message is shown to them)."""


def pick_rarity(odds, available, rng=random):
    """Weighted pick among the rarities that actually have cards."""
    choices = [r for r in odds if r in available] or [r for r in SLOT_ODDS if r in available]
    return rng.choices(choices, weights=[odds.get(r, SLOT_ODDS[r]) for r in choices])[0]


def open_pack(user, now=None):
    """Claim the user's pack and return its cards, rarest last."""
    now = now or timezone.now()
    with transaction.atomic():
        # A conditional UPDATE is the lock: two simultaneous requests can't both claim the pack.
        claimed = (
            User.objects.filter(pk=user.pk)
            .filter(Q(next_pack_at__isnull=True) | Q(next_pack_at__lte=now))
            .update(next_pack_at=now + PACK_COOLDOWN)
        )
        if not claimed:
            raise PackUnavailable("Your next pack isn't ready yet.")
        available = set(Card.objects.values_list("rarity", flat=True).distinct())
        if not available:
            raise PackUnavailable("No cards exist yet. Run the import first.")  # rolls back the claim
        slots = [SLOT_ODDS] * (PACK_SIZE - 1) + [HIT_ODDS]
        # ponytail: order_by("?") scans the rarity bucket; fine for ~2k cards, precompute ids if it grows.
        cards = [
            Card.objects.filter(rarity=pick_rarity(odds, available)).order_by("?").first()
            for odds in slots
        ]
        Pull.objects.bulk_create(Pull(user=user, card=card, opened_at=now) for card in cards)
    user.next_pack_at = now + PACK_COOLDOWN
    return sorted(cards, key=lambda card: card.rarity)
