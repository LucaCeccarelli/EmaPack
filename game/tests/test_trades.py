import uuid

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from game.friends import accept_request, remove_friendship, send_request
from game.models import Card, Pull, Trade, User
from game.trades import TradeError, accept_trade, propose_trade, remove_trade


def make_card(name):
    return Card.objects.create(komi_id=uuid.uuid4(), name=name)


def give(user, card):
    return Pull.objects.create(user=user, card=card, opened_at=timezone.now())


def owned(user):
    return sorted(user.pulls.values_list("card__name", flat=True))


class TradeLogicTests(TestCase):
    def setUp(self):
        self.ash = User.objects.create_user("ash", password="pw")
        self.gary = User.objects.create_user("gary", password="pw")
        self.friendship = send_request(self.ash, "gary")
        accept_request(self.gary, self.friendship.pk)
        self.bde, self.bds, self.cri, self.ski = (make_card(n) for n in ("BDE", "BDS", "CRI", "SKI"))
        give(self.ash, self.bde)
        give(self.ash, self.cri)
        give(self.gary, self.bds)
        give(self.gary, self.ski)

    def test_one_for_one_moves_a_single_copy_and_deletes_the_offer(self):
        give(self.ash, self.bde)  # ash has a spare: only one copy moves
        trade = propose_trade(self.ash, "gary", [self.bde.pk], [self.bds.pk])
        accept_trade(self.gary, trade.pk)
        self.assertEqual(owned(self.ash), ["BDE", "BDS", "CRI"])
        self.assertEqual(owned(self.gary), ["BDE", "SKI"])
        self.assertFalse(Trade.objects.exists())

    def test_many_for_many(self):
        trade = propose_trade(self.ash, "gary", [self.bde.pk, self.cri.pk], [self.bds.pk, self.ski.pk])
        accept_trade(self.gary, trade.pk)
        self.assertEqual(owned(self.ash), ["BDS", "SKI"])
        self.assertEqual(owned(self.gary), ["BDE", "CRI"])

    def test_gift_and_ask_have_one_empty_side(self):
        accept_trade(self.gary, propose_trade(self.ash, "gary", [self.bde.pk], []).pk)
        accept_trade(self.gary, propose_trade(self.ash, "gary", [], [self.ski.pk]).pk)
        self.assertEqual(owned(self.ash), ["CRI", "SKI"])
        self.assertEqual(owned(self.gary), ["BDE", "BDS"])

    def test_both_sides_empty_is_rejected(self):
        with self.assertRaises(TradeError):
            propose_trade(self.ash, "gary", [], [])

    def test_every_card_must_be_owned_by_its_side(self):
        for offered, requested in (
            ([self.bds.pk], []),  # ash offers gary's card
            ([], [self.bde.pk]),  # ash asks for his own card
            ([self.bde.pk, make_card("X").pk], []),  # one card nobody owns
            (["x"], []),  # tampered id
        ):
            with self.assertRaises(TradeError):
                propose_trade(self.ash, "gary", offered, requested)
        self.assertFalse(Trade.objects.exists())

    def test_cannot_trade_with_a_stranger(self):
        remove_friendship(self.ash, self.friendship.pk)
        with self.assertRaises(TradeError):
            propose_trade(self.ash, "gary", [self.bde.pk], [self.bds.pk])

    def test_only_the_recipient_can_accept(self):
        trade = propose_trade(self.ash, "gary", [self.bde.pk], [self.bds.pk])
        with self.assertRaises(TradeError):
            accept_trade(self.ash, trade.pk)
        self.assertEqual(owned(self.ash), ["BDE", "CRI"])

    def test_accept_cancels_if_any_card_is_gone(self):
        trade = propose_trade(self.ash, "gary", [self.bde.pk, self.cri.pk], [self.bds.pk])
        self.ash.pulls.filter(card=self.cri).delete()
        with self.assertRaises(TradeError):
            accept_trade(self.gary, trade.pk)
        self.assertEqual(owned(self.ash), ["BDE"])
        self.assertEqual(owned(self.gary), ["BDS", "SKI"])
        self.assertFalse(Trade.objects.exists())

    def test_same_copy_cannot_be_traded_twice(self):
        misty = User.objects.create_user("misty", password="pw")
        accept_request(misty, send_request(self.ash, "misty").pk)
        first = propose_trade(self.ash, "gary", [self.bde.pk], [])
        second = propose_trade(self.ash, "misty", [self.bde.pk], [])
        accept_trade(self.gary, first.pk)
        with self.assertRaises(TradeError):
            accept_trade(misty, second.pk)
        self.assertEqual(owned(misty), [])

    def test_accept_fails_once_unfriended(self):
        trade = propose_trade(self.ash, "gary", [self.bde.pk], [self.bds.pk])
        remove_friendship(self.gary, self.friendship.pk)
        with self.assertRaises(TradeError):
            accept_trade(self.gary, trade.pk)
        self.assertEqual(owned(self.gary), ["BDS", "SKI"])

    def test_either_side_can_remove_but_not_a_stranger(self):
        trade = propose_trade(self.ash, "gary", [self.bde.pk], [self.bds.pk])
        stranger = User.objects.create_user("brock", password="pw")
        with self.assertRaises(TradeError):
            remove_trade(stranger, trade.pk)
        remove_trade(self.gary, trade.pk)
        self.assertFalse(Trade.objects.exists())
