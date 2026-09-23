import random
import uuid
from datetime import timedelta

from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone

from game.models import Card, Pull, Rarity, User
from game.packs import HIT_ODDS, SLOT_ODDS, PackUnavailable, open_pack, pick_rarity


def make_card(rarity=Rarity.COMMON, name="card"):
    return Card.objects.create(komi_id=uuid.uuid4(), name=name, rarity=rarity)


class OpenPackTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ash", password="pw")
        self.now = timezone.now()

    def test_opens_five_cards_and_starts_cooldown(self):
        make_card()
        cards = open_pack(self.user, now=self.now)
        self.assertEqual(len(cards), 5)
        self.assertEqual(Pull.objects.filter(user=self.user).count(), 5)
        self.user.refresh_from_db()
        self.assertEqual(self.user.next_pack_at, self.now + settings.PACK_COOLDOWN)

    def test_cannot_open_twice_within_cooldown(self):
        make_card()
        open_pack(self.user, now=self.now)
        with self.assertRaises(PackUnavailable):
            open_pack(self.user, now=self.now + settings.PACK_COOLDOWN / 2)
        self.assertEqual(Pull.objects.count(), 5)

    def test_can_open_again_after_cooldown(self):
        make_card()
        open_pack(self.user, now=self.now)
        open_pack(self.user, now=self.now + settings.PACK_COOLDOWN)
        self.assertEqual(Pull.objects.count(), 10)

    @override_settings(PACK_COOLDOWN=timedelta(seconds=5))
    def test_cooldown_is_configurable(self):
        make_card()
        open_pack(self.user, now=self.now)
        with self.assertRaises(PackUnavailable):
            open_pack(self.user, now=self.now + timedelta(seconds=4))
        open_pack(self.user, now=self.now + timedelta(seconds=5))
        self.assertEqual(Pull.objects.count(), 10)

    def test_stale_user_instance_cannot_double_open(self):
        # Two requests holding the same user row: the DB decides, not the in-memory object.
        make_card()
        stale = User.objects.get(pk=self.user.pk)
        open_pack(self.user, now=self.now)
        with self.assertRaises(PackUnavailable):
            open_pack(stale, now=self.now)

    def test_no_cards_does_not_burn_cooldown(self):
        with self.assertRaises(PackUnavailable):
            open_pack(self.user, now=self.now)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.next_pack_at)

    def test_only_commons_still_fills_pack(self):
        make_card(Rarity.COMMON)
        self.assertEqual(len(open_pack(self.user, now=self.now)), 5)

    def test_last_card_is_rare_or_better_and_pack_is_sorted(self):
        for rarity in Rarity:
            make_card(rarity)
        for i in range(20):
            cards = open_pack(self.user, now=self.now + i * settings.PACK_COOLDOWN)
            rarities = [c.rarity for c in cards]
            self.assertEqual(rarities, sorted(rarities))
            self.assertGreaterEqual(rarities[-1], Rarity.RARE)


class PickRarityTests(TestCase):
    def test_only_returns_available_rarities(self):
        rng = random.Random(0)
        available = {Rarity.COMMON, Rarity.EPIC}
        picks = {pick_rarity(SLOT_ODDS, available, rng) for _ in range(200)}
        self.assertEqual(picks, available)

    def test_hit_slot_falls_back_when_no_rare_cards(self):
        rng = random.Random(0)
        self.assertEqual(pick_rarity(HIT_ODDS, {Rarity.COMMON}, rng), Rarity.COMMON)
