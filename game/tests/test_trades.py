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


class TradeViewTests(TestCase):
    def setUp(self):
        self.ash = User.objects.create_user("ash", password="pw")
        self.gary = User.objects.create_user("gary", password="pw")
        accept_request(self.gary, send_request(self.ash, "gary").pk)
        self.bde, self.bds, self.cri = (make_card(n) for n in ("BDE", "BDS", "CRI"))
        give(self.ash, self.bde)
        give(self.ash, self.cri)
        give(self.gary, self.bds)
        self.client.force_login(self.ash)
        self.url = reverse("trade_new", args=["gary"])

    def test_friend_card_page_links_to_the_trade_page(self):
        response = self.client.get(reverse("friend_card_detail", args=["gary", self.bds.pk]))
        self.assertContains(response, f'href="{self.url}?want={self.bds.pk}"')

    def test_trade_page_lists_both_sides_and_prechecks_wanted_card(self):
        response = self.client.get(self.url, {"want": self.bds.pk})
        self.assertContains(response, f'name="offered" value="{self.bde.pk}" aria-label="BDE, Common"')
        self.assertContains(response, f'name="requested" value="{self.bds.pk}" checked aria-label="BDS, Common"')
        self.assertContains(response, 'class="card rarity-common"', count=3)  # rendered like the collection

    def test_trade_page_404s_for_a_stranger(self):
        User.objects.create_user("brock", password="pw")
        self.assertEqual(self.client.get(reverse("trade_new", args=["brock"])).status_code, 404)

    def test_full_trade_through_the_ui(self):
        response = self.client.post(self.url, {"offered": [self.bde.pk, self.cri.pk], "requested": [self.bds.pk]})
        self.assertRedirects(response, reverse("friends"))
        self.assertContains(self.client.get(reverse("friends")), "Sent trade offers")

        self.client.force_login(self.gary)
        response = self.client.get(reverse("friends"))
        self.assertContains(response, "ash gives")
        self.assertContains(response, 'class="card rarity-common"', count=3)  # BDE + CRI for BDS, as mini cards
        self.client.post(reverse("trade_accept", args=[Trade.objects.get().pk]))
        self.assertEqual(owned(self.ash), ["BDS"])
        self.assertEqual(owned(self.gary), ["BDE", "CRI"])

    def test_gift_shows_nothing_on_the_empty_side(self):
        self.client.post(self.url, {"offered": [self.bde.pk]})
        self.client.force_login(self.gary)
        self.assertContains(self.client.get(reverse("friends")), '<span class="muted">nothing</span>')

    def test_invalid_offer_rerenders_with_boxes_still_ticked(self):
        response = self.client.post(self.url, {"offered": [self.bde.pk, "x"]})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You can only offer cards you own")
        self.assertContains(response, f'value="{self.bde.pk}" checked')
        self.assertFalse(Trade.objects.exists())

    def test_accept_and_remove_reject_get(self):
        self.assertEqual(self.client.get(reverse("trade_accept", args=[1])).status_code, 405)
        self.assertEqual(self.client.get(reverse("trade_remove", args=[1])).status_code, 405)

    def test_trade_offer_is_translated(self):
        propose_trade(self.ash, "gary", [self.bde.pk], [])
        self.client.force_login(self.gary)
        response = self.client.get(reverse("friends"), HTTP_ACCEPT_LANGUAGE="fr")
        self.assertContains(response, "Offres d'échange")
        self.assertContains(response, "ash donne")
        self.assertContains(response, "Vous donnez")
        self.assertContains(response, "rien")

    def test_trade_page_requires_login(self):
        self.client.logout()
        self.assertRedirects(self.client.get(self.url), f"{reverse('login')}?next={self.url}")

    def test_friends_page_has_a_trade_button_per_friend(self):
        self.assertContains(self.client.get(reverse("friends")), f'href="{self.url}"')

    def test_empty_offer_is_refused(self):
        response = self.client.post(self.url, {})
        self.assertContains(response, "Pick at least one card")
        self.assertFalse(Trade.objects.exists())

    def test_recipient_declines_through_the_ui(self):
        trade = propose_trade(self.ash, "gary", [self.bde.pk], [self.bds.pk])
        self.client.force_login(self.gary)
        response = self.client.post(reverse("trade_remove", args=[trade.pk]))
        self.assertRedirects(response, reverse("friends"))
        self.assertFalse(Trade.objects.exists())
        self.assertEqual(owned(self.gary), ["BDS"])

    def test_sender_cancels_through_the_ui(self):
        trade = propose_trade(self.ash, "gary", [self.bde.pk], [])
        self.client.post(reverse("trade_remove", args=[trade.pk]))
        self.assertFalse(Trade.objects.exists())
        self.assertNotContains(self.client.get(reverse("friends")), "Sent trade offers")

    def test_sender_cannot_accept_their_own_offer_through_the_ui(self):
        trade = propose_trade(self.ash, "gary", [self.bde.pk], [self.bds.pk])
        response = self.client.post(reverse("trade_accept", args=[trade.pk]), follow=True)
        self.assertContains(response, "no longer exists")
        self.assertEqual(owned(self.ash), ["BDE", "CRI"])

    def test_accepting_a_stale_offer_flashes_and_removes_it(self):
        trade = propose_trade(self.ash, "gary", [self.bde.pk], [self.bds.pk])
        self.ash.pulls.filter(card=self.bde).delete()
        self.client.force_login(self.gary)
        response = self.client.post(reverse("trade_accept", args=[trade.pk]), follow=True)
        self.assertContains(response, "no longer available")
        self.assertNotContains(response, "Trade offers")

    def test_accepting_twice_only_trades_once(self):
        trade = propose_trade(self.ash, "gary", [self.bde.pk], [self.bds.pk])
        self.client.force_login(self.gary)
        self.client.post(reverse("trade_accept", args=[trade.pk]))
        response = self.client.post(reverse("trade_accept", args=[trade.pk]), follow=True)
        self.assertContains(response, "no longer exists")
        self.assertEqual(owned(self.gary), ["BDE"])
