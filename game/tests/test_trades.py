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
        self.bde, self.bds = make_card("BDE"), make_card("BDS")
        give(self.ash, self.bde)
        give(self.gary, self.bds)

    def test_accept_swaps_one_copy_each_way_and_deletes_the_offer(self):
        give(self.ash, self.bde)  # ash has a spare: only one copy moves
        trade = propose_trade(self.ash, "gary", self.bds.pk, self.bde.pk)
        accept_trade(self.gary, trade.pk)
        self.assertEqual(owned(self.ash), ["BDE", "BDS"])
        self.assertEqual(owned(self.gary), ["BDE"])
        self.assertFalse(Trade.objects.exists())

    def test_cannot_trade_with_a_stranger(self):
        remove_friendship(self.ash, self.friendship.pk)
        with self.assertRaises(TradeError):
            propose_trade(self.ash, "gary", self.bds.pk, self.bde.pk)

    def test_must_own_the_offered_card_and_friend_the_requested_one(self):
        with self.assertRaises(TradeError):
            propose_trade(self.ash, "gary", self.bds.pk, self.bds.pk)
        with self.assertRaises(TradeError):
            propose_trade(self.ash, "gary", self.bde.pk, self.bde.pk)

    def test_only_the_recipient_can_accept(self):
        trade = propose_trade(self.ash, "gary", self.bds.pk, self.bde.pk)
        with self.assertRaises(TradeError):
            accept_trade(self.ash, trade.pk)
        self.assertEqual(owned(self.ash), ["BDE"])

    def test_accept_fails_and_cancels_if_a_card_is_gone(self):
        trade = propose_trade(self.ash, "gary", self.bds.pk, self.bde.pk)
        self.ash.pulls.all().delete()
        with self.assertRaises(TradeError):
            accept_trade(self.gary, trade.pk)
        self.assertEqual(owned(self.gary), ["BDS"])
        self.assertFalse(Trade.objects.exists())

    def test_same_copy_cannot_be_traded_twice(self):
        misty = User.objects.create_user("misty", password="pw")
        accept_request(misty, send_request(self.ash, "misty").pk)
        give(misty, self.bds)
        first = propose_trade(self.ash, "gary", self.bds.pk, self.bde.pk)
        second = propose_trade(self.ash, "misty", self.bds.pk, self.bde.pk)
        accept_trade(self.gary, first.pk)
        with self.assertRaises(TradeError):
            accept_trade(misty, second.pk)
        self.assertEqual(owned(misty), ["BDS"])

    def test_accept_fails_once_unfriended(self):
        trade = propose_trade(self.ash, "gary", self.bds.pk, self.bde.pk)
        remove_friendship(self.gary, self.friendship.pk)
        with self.assertRaises(TradeError):
            accept_trade(self.gary, trade.pk)
        self.assertEqual(owned(self.gary), ["BDS"])

    def test_either_side_can_remove_but_not_a_stranger(self):
        trade = propose_trade(self.ash, "gary", self.bds.pk, self.bde.pk)
        stranger = User.objects.create_user("brock", password="pw")
        with self.assertRaises(TradeError):
            remove_trade(stranger, trade.pk)
        remove_trade(self.gary, trade.pk)
        self.assertFalse(Trade.objects.exists())
