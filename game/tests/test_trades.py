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


class TradeViewTests(TestCase):
    def setUp(self):
        self.ash = User.objects.create_user("ash", password="pw")
        self.gary = User.objects.create_user("gary", password="pw")
        accept_request(self.gary, send_request(self.ash, "gary").pk)
        self.bde, self.bds = make_card("BDE"), make_card("BDS")
        give(self.ash, self.bde)
        give(self.gary, self.bds)
        self.client.force_login(self.ash)

    def test_friend_card_page_offers_my_cards(self):
        response = self.client.get(reverse("friend_card_detail", args=["gary", self.bds.pk]))
        self.assertContains(response, f'action="{reverse("trade_propose", args=["gary", self.bds.pk])}"')
        self.assertContains(response, f'<option value="{self.bde.pk}">BDE')

    def test_own_card_page_has_no_trade_form(self):
        response = self.client.get(reverse("card_detail", args=[self.bde.pk]))
        self.assertNotContains(response, "trade-form")

    def test_full_trade_through_the_ui(self):
        response = self.client.post(reverse("trade_propose", args=["gary", self.bds.pk]), {"offered": self.bde.pk})
        self.assertRedirects(response, reverse("friends"))
        self.assertContains(self.client.get(reverse("friends")), "Sent trade offers")

        self.client.force_login(self.gary)
        self.assertContains(self.client.get(reverse("friends")), "Trade offers")
        trade = Trade.objects.get()
        self.client.post(reverse("trade_accept", args=[trade.pk]))
        self.assertEqual(owned(self.ash), ["BDS"])
        self.assertEqual(owned(self.gary), ["BDE"])

    def test_tampered_offer_is_flashed_not_crashing(self):
        response = self.client.post(reverse("trade_propose", args=["gary", self.bds.pk]), {"offered": "x"}, follow=True)
        self.assertContains(response, "Pick a card you own")
        self.assertFalse(Trade.objects.exists())

    def test_trade_endpoints_reject_get(self):
        self.assertEqual(self.client.get(reverse("trade_propose", args=["gary", self.bds.pk])).status_code, 405)
        self.assertEqual(self.client.get(reverse("trade_accept", args=[1])).status_code, 405)
        self.assertEqual(self.client.get(reverse("trade_remove", args=[1])).status_code, 405)

    def test_trade_offer_is_translated(self):
        propose_trade(self.ash, "gary", self.bds.pk, self.bde.pk)
        self.client.force_login(self.gary)
        response = self.client.get(reverse("friends"), HTTP_ACCEPT_LANGUAGE="fr")
        self.assertContains(response, "Offres d'échange")
        self.assertContains(response, "<strong>ash</strong> donne BDE")
