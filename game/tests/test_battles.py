import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from game.battles import (
    CHALLENGE_TTL, PICK_TIME, STATS, BattleError, accept_challenge, challenge, deck_problem,
    remove_challenge, save_deck,
)
from game.models import Battle, Card, Friendship, Pull, Rarity, User


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


T0 = timezone.now()


class ChallengeTests(TestCase):
    def setUp(self):
        self.ash, self.gary, self.misty = (User.objects.create_user(n, password="pw") for n in ("ash", "gary", "misty"))
        self.decks = {}
        for u in (self.ash, self.gary, self.misty):
            cards = [make_card(f"{u.username}{i}", subs=i, posts=i + 1, events=i + 2) for i in range(5)]
            for c in cards:
                give(u, c)
            save_deck(u, [str(c.pk) for c in cards])
            self.decks[u] = cards
        for a, b in ((self.ash, self.gary), (self.misty, self.gary)):
            Friendship.objects.create(from_user=a, to_user=b, status=Friendship.Status.ACCEPTED)

    def test_challenge_creates_pending_battle(self):
        b = challenge(self.ash, "gary", now=T0)
        self.assertEqual((b.challenger, b.opponent, b.status), (self.ash, self.gary, Battle.Status.PENDING))

    def test_only_friends(self):
        User.objects.create_user("stranger", password="pw")
        with self.assertRaises(BattleError):
            challenge(self.ash, "stranger", now=T0)

    def test_needs_valid_deck(self):
        self.ash.deck.clear()
        with self.assertRaises(BattleError):
            challenge(self.ash, "gary", now=T0)

    def test_cannot_challenge_yourself(self):
        with self.assertRaises(BattleError):
            challenge(self.ash, "ash", now=T0)

    def test_busy_when_target_has_incoming(self):
        challenge(self.ash, "gary", now=T0)
        with self.assertRaises(BattleError):
            challenge(self.misty, "gary", now=T0)

    def test_busy_when_challenger_has_incoming(self):
        challenge(self.ash, "gary", now=T0)
        with self.assertRaises(BattleError):
            challenge(self.gary, "misty", now=T0)

    def test_expired_challenge_frees_players(self):
        challenge(self.ash, "gary", now=T0)
        b = challenge(self.misty, "gary", now=T0 + CHALLENGE_TTL + timedelta(seconds=1))
        self.assertEqual(b.challenger, self.misty)

    def test_accept_snapshots_decks_and_starts_round_one(self):
        b = accept_challenge(self.gary, challenge(self.ash, "gary", now=T0).pk, now=T0)
        self.assertEqual(b.status, Battle.Status.ACTIVE)
        ash_deck = self.decks[self.ash]
        self.assertEqual(set(b.challenger_deck), {str(c.pk) for c in ash_deck})
        c = ash_deck[2]
        self.assertEqual(b.challenger_deck[str(c.pk)]["post_count"], c.post_count)
        self.assertEqual(set(b.opponent_deck), {str(c.pk) for c in self.decks[self.gary]})
        r = b.rounds.get()
        self.assertEqual((r.number, r.deadline), (1, T0 + PICK_TIME))
        self.assertIn(r.stat, STATS)

    def test_snapshot_ignores_later_deck_edits(self):
        b = accept_challenge(self.gary, challenge(self.ash, "gary", now=T0).pk, now=T0)
        extra = [make_card(f"x{i}") for i in range(5)]
        for c in extra:
            give(self.ash, c)
        save_deck(self.ash, [str(c.pk) for c in extra])
        b.refresh_from_db()
        self.assertEqual(set(b.challenger_deck), {str(c.pk) for c in self.decks[self.ash]})

    def test_only_opponent_can_accept(self):
        b = challenge(self.ash, "gary", now=T0)
        with self.assertRaises(BattleError):
            accept_challenge(self.ash, b.pk, now=T0)

    def test_expired_challenge_cannot_be_accepted(self):
        b = challenge(self.ash, "gary", now=T0)
        with self.assertRaises(BattleError):
            accept_challenge(self.gary, b.pk, now=T0 + CHALLENGE_TTL + timedelta(seconds=1))

    def test_accept_with_stale_challenger_deck_deletes_challenge(self):
        b = challenge(self.ash, "gary", now=T0)
        self.ash.pulls.filter(card=self.decks[self.ash][0]).delete()
        with self.assertRaises(BattleError):
            accept_challenge(self.gary, b.pk, now=T0)
        self.assertFalse(Battle.objects.filter(pk=b.pk).exists())

    def test_decline_and_cancel(self):
        b = challenge(self.ash, "gary", now=T0)
        with self.assertRaises(BattleError):
            remove_challenge(self.misty, b.pk)
        remove_challenge(self.gary, b.pk)
        self.assertFalse(Battle.objects.exists())
        b = challenge(self.ash, "gary", now=T0)
        remove_challenge(self.ash, b.pk)
        self.assertFalse(Battle.objects.exists())

    def test_cannot_remove_active_battle(self):
        b = accept_challenge(self.gary, challenge(self.ash, "gary", now=T0).pk, now=T0)
        with self.assertRaises(BattleError):
            remove_challenge(self.ash, b.pk)
