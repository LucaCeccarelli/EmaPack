import json
import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from game.battles import (
    CHALLENGE_TTL, PICK_TIME, REVEAL_TIME, ROUNDS, STATS, BattleError, accept_challenge, advance, challenge,
    battle_state, deck_problem, play_card, record, remaining_cards, remove_challenge, save_deck, scores,
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


S5 = timedelta(seconds=5)


class PlayTests(TestCase):
    def setUp(self):
        self.ash, self.gary, self.misty = (User.objects.create_user(n, password="pw") for n in ("ash", "gary", "misty"))
        Friendship.objects.create(from_user=self.ash, to_user=self.gary, status=Friendship.Status.ACCEPTED)
        # strong beats weak on every stat; tie_a/tie_b are equal on every stat
        self.strong = self.deck(self.ash, 100)
        self.weak = self.deck(self.gary, 1)

    def deck(self, user, v):
        cards = [make_card(f"{user.username}{i}", subs=v, posts=v, events=v) for i in range(5)]
        for c in cards:
            give(user, c)
        save_deck(user, [str(c.pk) for c in cards])
        return cards

    def start(self, now=T0):
        return accept_challenge(self.gary, challenge(self.ash, "gary", now=now).pk, now=now)

    def play_round(self, b, ash_card, gary_card, now=T0):
        n = b.rounds.last().number
        play_card(self.ash, b.pk, str(ash_card.pk), n, now=now)
        play_card(self.gary, b.pk, str(gary_card.pk), n, now=now)
        b.refresh_from_db()

    def test_higher_value_wins_round_and_next_round_starts(self):
        b = self.start()
        play_card(self.ash, b.pk, str(self.strong[0].pk), 1, now=T0)
        play_card(self.gary, b.pk, str(self.weak[0].pk), 1, now=T0 + S5)
        self.assertEqual(scores(b), (1, 0))
        self.assertEqual(b.rounds.get(number=2).deadline, T0 + S5 + REVEAL_TIME + PICK_TIME)

    def test_equal_values_draw_the_round(self):
        self.weak = self.deck(self.gary, 100)
        b = self.start()
        self.play_round(b, self.strong[0], self.weak[0])
        self.assertEqual(scores(b), (0, 0))
        self.assertEqual(b.rounds.count(), 2)

    def test_battle_stops_when_trailing_player_cannot_draw(self):
        b = self.start()
        for i in range(3):
            self.play_round(b, self.strong[i], self.weak[i])
        self.assertEqual((b.status, b.winner), (Battle.Status.FINISHED, self.ash))
        self.assertEqual(b.rounds.count(), 3)

    def test_battle_continues_while_draw_still_possible(self):
        b = self.start()
        for i in range(2):
            self.play_round(b, self.strong[i], self.weak[i])
        self.assertEqual(b.status, Battle.Status.ACTIVE)

    def test_all_rounds_drawn_is_a_drawn_battle(self):
        self.weak = self.deck(self.gary, 100)
        b = self.start()
        for i in range(ROUNDS):
            self.play_round(b, self.strong[i], self.weak[i])
        self.assertEqual((b.status, b.winner, b.rounds.count()), (Battle.Status.FINISHED, None, ROUNDS))

    def test_cannot_play_twice_in_a_round(self):
        b = self.start()
        play_card(self.ash, b.pk, str(self.strong[0].pk), 1, now=T0)
        with self.assertRaises(BattleError):
            play_card(self.ash, b.pk, str(self.strong[1].pk), 1, now=T0)
        self.assertEqual(b.rounds.get(number=1).challenger_card, self.strong[0])

    def test_cannot_replay_a_card(self):
        b = self.start()
        self.play_round(b, self.strong[0], self.weak[0])
        with self.assertRaises(BattleError):
            play_card(self.ash, b.pk, str(self.strong[0].pk), 1, now=T0)
        self.assertIsNone(b.rounds.get(number=2).challenger_card)

    def test_cannot_play_card_outside_deck_or_tampered(self):
        b = self.start()
        for bad in (str(self.weak[0].pk), "abc", ""):
            with self.assertRaises(BattleError):
                play_card(self.ash, b.pk, bad, 1, now=T0)
        self.assertIsNone(b.rounds.get(number=1).challenger_card)

    def test_outsider_cannot_play(self):
        b = self.start()
        with self.assertRaises(BattleError):
            play_card(self.misty, b.pk, str(self.strong[0].pk), 1, now=T0)
        self.assertEqual(b.rounds.filter(challenger_card__isnull=False).count(), 0)
        self.assertEqual(b.rounds.filter(opponent_card__isnull=False).count(), 0)

    def test_timeout_auto_plays_missing_side(self):
        b = self.start()
        play_card(self.ash, b.pk, str(self.strong[0].pk), 1, now=T0)
        advance(b, T0 + PICK_TIME + S5 / 5)
        r1 = b.rounds.get(number=1)
        self.assertIn(str(r1.opponent_card_id), b.opponent_deck)
        self.assertEqual(r1.challenger_card, self.strong[0])
        self.assertEqual(b.rounds.get(number=2).deadline, T0 + PICK_TIME + REVEAL_TIME + PICK_TIME)

    def test_late_pick_is_rejected(self):
        b = self.start()
        play_card(self.ash, b.pk, str(self.strong[0].pk), 1, now=T0)
        late = T0 + PICK_TIME + S5 / 5
        advance(b, late)
        auto = b.rounds.get(number=1).opponent_card_id
        fresh = next(c for c in self.weak if c.pk != auto)
        with self.assertRaises(BattleError):
            play_card(self.gary, b.pk, str(fresh.pk), 1, now=late)
        self.assertIsNone(b.rounds.get(number=2).opponent_card)

    def test_pick_for_wrong_round_number_is_rejected(self):
        b = self.start()
        for bad in (2, "x", None):
            with self.assertRaises(BattleError):
                play_card(self.ash, b.pk, str(self.strong[0].pk), bad, now=T0)
        self.assertIsNone(b.rounds.get(number=1).challenger_card)

    def test_advance_catches_up_every_overdue_round(self):
        b = self.start()
        advance(b, T0 + timedelta(minutes=10))
        self.assertEqual(b.status, Battle.Status.FINISHED)
        rounds = list(b.rounds.all())
        self.assertGreaterEqual(len(rounds), 3)
        for side in ("challenger", "opponent"):
            ids = [getattr(r, f"{side}_card_id") for r in rounds]
            self.assertNotIn(None, ids)
            self.assertEqual(len(set(ids)), len(ids))
        self.assertEqual(remaining_cards(b, "challenger"), [c for c in b.challenger_deck if int(c) not in
                         [r.challenger_card_id for r in rounds]])

    def test_abandoned_battle_finishes_on_next_challenge(self):
        b = self.start()
        challenge(self.ash, "gary", now=T0 + timedelta(minutes=10))
        b.refresh_from_db()
        self.assertEqual(b.status, Battle.Status.FINISHED)

    def test_record(self):
        for winner_strong in (True, False, None):
            if winner_strong is None:
                self.weak = self.deck(self.gary, 100)
                self.strong = self.deck(self.ash, 100)
            elif not winner_strong:
                self.strong, self.weak = self.deck(self.ash, 1), self.deck(self.gary, 100)
            b = self.start()
            for i in range(ROUNDS):
                if b.status != Battle.Status.ACTIVE:
                    break
                self.play_round(b, self.strong[i], self.weak[i])
        self.assertEqual(record(self.ash), {"wins": 1, "losses": 1, "draws": 1})
        self.assertEqual(record(self.gary), {"wins": 1, "losses": 1, "draws": 1})
        self.assertEqual(record(self.misty), {"wins": 0, "losses": 0, "draws": 0})


class StateTests(PlayTests):
    """Reuses PlayTests' setup/helpers; ash is the challenger. Test names differ, so PlayTests' own tests rerun here harmlessly."""

    def test_opponent_unplayed_cards_never_appear(self):
        b = self.start()
        for user in (self.ash, self.gary):
            s = battle_state(user, b, now=T0)
            theirs = self.weak if user == self.ash else self.strong
            for c in theirs:
                self.assertNotIn(c.name, json.dumps(s))
                self.assertNotIn(str(c.pk), [str(h["id"]) for h in s["hand"]])
            self.assertEqual(s["opponent_cards_left"], 5)
        self.assertEqual(battle_state(self.ash, b, now=T0)["status"], "active")
        self.assertEqual(len(battle_state(self.ash, b, now=T0)["hand"]), 5)

    def test_opponent_pick_hidden_until_both_played(self):
        b = self.start()
        play_card(self.gary, b.pk, str(self.weak[0].pk), 1, now=T0)
        s = battle_state(self.ash, b, now=T0)
        self.assertTrue(s["round"]["opponent_picked"])
        self.assertFalse(s["round"]["you_picked"])
        self.assertNotIn(self.weak[0].name, json.dumps(s))
        self.assertEqual(s["opponent_cards_left"], 5)  # the pick still counts as unplayed

    def test_revealed_card_appears_in_history_after_both_play(self):
        b = self.start()
        self.play_round(b, self.strong[0], self.weak[0])
        s = battle_state(self.ash, b, now=T0)
        h = s["history"][0]
        self.assertEqual((h["number"], h["result"], h["opponent"]["id"], h["you"]["id"]),
                         (1, "win", self.weak[0].pk, self.strong[0].pk))
        self.assertEqual((h["you"]["value"], h["opponent"]["value"]), (100, 1))
        self.assertIn(self.weak[0].name, h["opponent"]["html"])
        self.assertEqual(s["score"], {"you": 1, "opponent": 0})
        self.assertEqual(battle_state(self.gary, b, now=T0)["history"][0]["result"], "loss")
        self.assertEqual(s["opponent_cards_left"], 4)
        self.assertEqual(s["round"]["number"], 2)
        self.assertNotIn(self.weak[1].name, json.dumps(s))

    def test_history_values_come_from_snapshot(self):
        b = self.start()
        self.play_round(b, self.strong[0], self.weak[0])
        Card.objects.filter(pk=self.weak[0].pk).update(subscriber_count=5000, post_count=5000, event_count=5000)
        h = battle_state(self.ash, b, now=T0)["history"][0]
        self.assertEqual(h["opponent"]["value"], 1)

    def test_draw_result_in_history(self):
        self.weak = self.deck(self.gary, 100)
        b = self.start()
        self.play_round(b, self.strong[0], self.weak[0])
        self.assertEqual(battle_state(self.ash, b, now=T0)["history"][0]["result"], "draw")

    def test_hand_excludes_played_and_current_pick(self):
        b = self.start()
        self.play_round(b, self.strong[0], self.weak[0])
        play_card(self.ash, b.pk, str(self.strong[1].pk), 2, now=T0)
        s = battle_state(self.ash, b, now=T0)
        self.assertEqual({h["id"] for h in s["hand"]}, {c.pk for c in self.strong[2:]})
        self.assertTrue(s["round"]["you_picked"])

    def test_finished_state_has_result_and_no_round(self):
        b = self.start()
        for i in range(3):
            self.play_round(b, self.strong[i], self.weak[i])
        s, g = battle_state(self.ash, b, now=T0), battle_state(self.gary, b, now=T0)
        self.assertEqual((s["status"], s["result"], s["round"], s["hand"]), ("finished", "win", None, []))
        self.assertEqual((g["result"], g["is_challenger"], g["opponent"]), ("loss", False, "ash"))
        self.assertEqual(len(s["history"]), 3)
        for c in self.weak[3:]:  # never played: still secret
            self.assertNotIn(c.name, json.dumps(s))

    def test_pending_state(self):
        b = challenge(self.ash, "gary", now=T0)
        s = battle_state(self.gary, b, now=T0)
        self.assertEqual((s["status"], s["round"], s["hand"], s["history"], s["result"]), ("pending", None, [], [], None))
        for c in self.strong:
            self.assertNotIn(c.name, json.dumps(s))

    def test_state_settles_overdue_round(self):
        b = self.start()
        s = battle_state(self.ash, b, now=T0 + PICK_TIME + S5)
        self.assertEqual(len(s["history"]), 1)

    def test_outsider_gets_no_state(self):
        b = self.start()
        with self.assertRaises(BattleError):
            battle_state(self.misty, b, now=T0)
