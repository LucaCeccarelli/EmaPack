import uuid

from django.test import TestCase
from django.utils import timezone

from game.battles import BattleError, deck_problem, save_deck
from game.models import Card, Pull, Rarity, User


def make_card(name, rarity=Rarity.COMMON, subs=0, posts=0, events=0):
    return Card.objects.create(
        komi_id=uuid.uuid4(), name=name, rarity=rarity,
        subscriber_count=subs, post_count=posts, event_count=events,
    )


def give(user, card):
    return Pull.objects.create(user=user, card=card, opened_at=timezone.now())


class DeckTests(TestCase):
    def setUp(self):
        self.ash = User.objects.create_user("ash", password="pw")
        self.cards = [make_card(f"c{i}") for i in range(1, 7)]
        for c in self.cards:
            give(self.ash, c)

    def ids(self, cards):
        return [str(c.pk) for c in cards]

    def test_save_deck_with_five_owned_distinct_cards(self):
        save_deck(self.ash, self.ids(self.cards[:5]))
        self.assertEqual(set(self.ash.deck.all()), set(self.cards[:5]))
        self.assertIsNone(deck_problem(self.ash))

    def test_rejects_wrong_size(self):
        save_deck(self.ash, self.ids(self.cards[:5]))
        for n in (4, 6):
            with self.assertRaises(BattleError):
                save_deck(self.ash, self.ids(self.cards[:n]))
        self.assertEqual(set(self.ash.deck.all()), set(self.cards[:5]))

    def test_rejects_unowned_card(self):
        other = make_card("other")
        with self.assertRaises(BattleError):
            save_deck(self.ash, self.ids(self.cards[:4] + [other]))

    def test_rejects_tampered_id(self):
        with self.assertRaises(BattleError):
            save_deck(self.ash, ["abc"])

    def test_duplicate_ids_count_once(self):
        ids = self.ids([self.cards[0]] + self.cards[:4])
        with self.assertRaises(BattleError):
            save_deck(self.ash, ids)

    def test_rarity_cap(self):
        legs = [make_card(f"L{i}", Rarity.LEGENDARY) for i in range(2)]
        epics = [make_card(f"E{i}", Rarity.EPIC) for i in range(3)]
        for c in legs + epics:
            give(self.ash, c)
        with self.assertRaises(BattleError):
            save_deck(self.ash, self.ids(legs + self.cards[:3]))
        with self.assertRaises(BattleError):
            save_deck(self.ash, self.ids(epics + self.cards[:2]))
        save_deck(self.ash, self.ids(legs[:1] + epics[:2] + self.cards[:2]))
        self.assertIsNone(deck_problem(self.ash))

    def test_empty_deck_has_a_problem(self):
        self.assertTrue(deck_problem(User.objects.create_user("new", password="pw")))

    def test_deck_goes_stale_when_card_leaves_collection(self):
        save_deck(self.ash, self.ids(self.cards[:5]))
        self.ash.pulls.filter(card=self.cards[0]).delete()
        self.assertIsNotNone(deck_problem(self.ash))

    def test_deck_goes_stale_when_rarity_rises_past_cap(self):
        leg = make_card("L", Rarity.LEGENDARY)
        give(self.ash, leg)
        save_deck(self.ash, self.ids([leg] + self.cards[:4]))
        Card.objects.filter(pk=self.cards[0].pk).update(rarity=Rarity.LEGENDARY)
        self.assertIsNotNone(deck_problem(self.ash))
