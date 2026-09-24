import uuid

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from game.friends import FriendError, accept_request, are_friends, friends_of, remove_friendship, send_request
from game.models import Card, Friendship, Pull, Rarity, User


def make_card(name="BDE", rarity=Rarity.COMMON):
    return Card.objects.create(komi_id=uuid.uuid4(), name=name, rarity=rarity)


class FriendshipModelTests(TestCase):
    def test_same_pair_cannot_be_requested_twice(self):
        a = User.objects.create_user("ash", password="pw")
        b = User.objects.create_user("gary", password="pw")
        Friendship.objects.create(from_user=a, to_user=b)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Friendship.objects.create(from_user=a, to_user=b)

    def test_new_request_defaults_to_pending(self):
        a = User.objects.create_user("ash", password="pw")
        b = User.objects.create_user("gary", password="pw")
        friendship = Friendship.objects.create(from_user=a, to_user=b)
        self.assertEqual(friendship.status, Friendship.Status.PENDING)


class FriendLogicTests(TestCase):
    def setUp(self):
        self.ash = User.objects.create_user("ash", password="pw")
        self.gary = User.objects.create_user("gary", password="pw")

    def test_send_request_creates_a_pending_friendship(self):
        friendship = send_request(self.ash, "gary")
        self.assertEqual(
            (friendship.from_user, friendship.to_user, friendship.status),
            (self.ash, self.gary, Friendship.Status.PENDING),
        )

    def test_send_request_is_case_insensitive(self):
        send_request(self.ash, "GARY")
        self.assertTrue(Friendship.objects.filter(from_user=self.ash, to_user=self.gary).exists())

    def test_cannot_add_yourself(self):
        with self.assertRaises(FriendError):
            send_request(self.ash, "ash")
        self.assertFalse(Friendship.objects.exists())

    def test_unknown_username_raises(self):
        with self.assertRaises(FriendError):
            send_request(self.ash, "nobody")

    def test_cannot_send_a_second_pending_request(self):
        send_request(self.ash, "gary")
        with self.assertRaises(FriendError):
            send_request(self.ash, "gary")

    def test_crossed_requests_auto_accept(self):
        send_request(self.ash, "gary")
        friendship = send_request(self.gary, "ash")
        self.assertEqual(friendship.status, Friendship.Status.ACCEPTED)
        self.assertTrue(are_friends(self.ash, self.gary))

    def test_cannot_send_request_to_an_existing_friend(self):
        friendship = send_request(self.ash, "gary")
        accept_request(self.gary, friendship.pk)
        with self.assertRaises(FriendError):
            send_request(self.ash, "gary")

    def test_are_friends_is_symmetric(self):
        friendship = send_request(self.ash, "gary")
        accept_request(self.gary, friendship.pk)
        self.assertTrue(are_friends(self.ash, self.gary))
        self.assertTrue(are_friends(self.gary, self.ash))

    def test_are_friends_false_while_pending(self):
        send_request(self.ash, "gary")
        self.assertFalse(are_friends(self.ash, self.gary))

    def test_only_the_recipient_can_accept(self):
        friendship = send_request(self.ash, "gary")
        with self.assertRaises(FriendError):
            accept_request(self.ash, friendship.pk)

    def test_friends_of_lists_both_directions(self):
        friendship = send_request(self.ash, "gary")
        accept_request(self.gary, friendship.pk)
        self.assertEqual([u.username for u in friends_of(self.ash)], ["gary"])
        self.assertEqual([u.username for u in friends_of(self.gary)], ["ash"])

    def test_remove_friendship_deletes_it(self):
        friendship = send_request(self.ash, "gary")
        remove_friendship(self.gary, friendship.pk)
        self.assertFalse(Friendship.objects.exists())

    def test_remove_friendship_requires_being_a_party(self):
        friendship = send_request(self.ash, "gary")
        stranger = User.objects.create_user("brock", password="pw")
        with self.assertRaises(FriendError):
            remove_friendship(stranger, friendship.pk)


class FriendViewTests(TestCase):
    def setUp(self):
        self.ash = User.objects.create_user("ash", password="pw")
        self.gary = User.objects.create_user("gary", password="pw")
        self.client.force_login(self.ash)

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("friends"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('friends')}")

    def test_nav_link_is_present(self):
        self.assertContains(self.client.get(reverse("home")), f'href="{reverse("friends")}"')

    def test_page_lists_sections(self):
        response = self.client.get(reverse("friends"))
        self.assertContains(response, "Add a friend")
        self.assertContains(response, "No friends yet")

    def test_send_request_via_form(self):
        response = self.client.post(reverse("friends"), {"username": "gary"})
        self.assertRedirects(response, reverse("friends"))
        self.assertTrue(
            Friendship.objects.filter(
                from_user=self.ash, to_user=self.gary, status=Friendship.Status.PENDING
            ).exists()
        )
        self.assertContains(self.client.get(reverse("friends")), "gary")

    def test_send_request_error_is_flashed(self):
        response = self.client.post(reverse("friends"), {"username": "nobody"}, follow=True)
        self.assertContains(response, "No player named")

    def test_recipient_sees_incoming_request(self):
        send_request(self.ash, "gary")
        self.client.force_login(self.gary)
        response = self.client.get(reverse("friends"))
        self.assertContains(response, "ash")
        self.assertContains(response, "Accept")

    def test_accept_makes_them_friends(self):
        friendship = send_request(self.ash, "gary")
        self.client.force_login(self.gary)
        response = self.client.post(reverse("friend_accept", args=[friendship.pk]))
        self.assertRedirects(response, reverse("friends"))
        friendship.refresh_from_db()
        self.assertEqual(friendship.status, Friendship.Status.ACCEPTED)

    def test_sender_cannot_accept_own_request(self):
        friendship = send_request(self.ash, "gary")
        self.client.post(reverse("friend_accept", args=[friendship.pk]))
        friendship.refresh_from_db()
        self.assertEqual(friendship.status, Friendship.Status.PENDING)

    def test_remove_deletes_the_row(self):
        friendship = send_request(self.ash, "gary")
        response = self.client.post(reverse("friend_remove", args=[friendship.pk]))
        self.assertRedirects(response, reverse("friends"))
        self.assertFalse(Friendship.objects.exists())

    def test_accept_and_remove_reject_get(self):
        friendship = send_request(self.ash, "gary")
        self.assertEqual(self.client.get(reverse("friend_accept", args=[friendship.pk])).status_code, 405)
        self.assertEqual(self.client.get(reverse("friend_remove", args=[friendship.pk])).status_code, 405)


class FriendCollectionViewTests(TestCase):
    def setUp(self):
        self.ash = User.objects.create_user("ash", password="pw")
        self.gary = User.objects.create_user("gary", password="pw")
        self.client.force_login(self.ash)

    def test_404_for_a_stranger(self):
        response = self.client.get(reverse("friend_collection", args=["gary"]))
        self.assertEqual(response.status_code, 404)

    def test_404_while_request_still_pending(self):
        send_request(self.ash, "gary")
        response = self.client.get(reverse("friend_collection", args=["gary"]))
        self.assertEqual(response.status_code, 404)

    def test_shows_the_friend_s_cards_read_only(self):
        friendship = send_request(self.ash, "gary")
        accept_request(self.gary, friendship.pk)
        card = make_card(name="BDE")
        Pull.objects.create(user=self.gary, card=card, opened_at=timezone.now())
        response = self.client.get(reverse("friend_collection", args=["gary"]))
        self.assertContains(response, "BDE")
        self.assertContains(response, "gary")
        self.assertNotContains(response, f'href="{reverse("card_detail", args=[card.pk])}"')

    def test_unknown_username_404s(self):
        response = self.client.get(reverse("friend_collection", args=["nobody"]))
        self.assertEqual(response.status_code, 404)
