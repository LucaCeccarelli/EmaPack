import uuid

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from game.models import Card, Pull, Rarity, User


def make_card(rarity=Rarity.COMMON, name="BDE", description=""):
    return Card.objects.create(komi_id=uuid.uuid4(), name=name, rarity=rarity, description=description)


class AuthTests(TestCase):
    def test_signup_logs_in_and_redirects_home(self):
        response = self.client.post(
            reverse("signup"),
            {"username": "ash", "password1": "pikachu-2026!", "password2": "pikachu-2026!"},
        )
        self.assertRedirects(response, reverse("home"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), User.objects.get().pk)

    def test_pages_require_login(self):
        for name in ["home", "collection"]:
            response = self.client.get(reverse(name))
            self.assertRedirects(response, f"{reverse('login')}?next={reverse(name)}")


class GameViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ash", password="pw")
        self.client.force_login(self.user)

    def test_home_exposes_open_url_and_cooldown(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, f'data-open-url="{reverse("open_pack")}"')
        self.assertContains(response, 'data-next-pack-at=""')

    def test_open_pack_returns_five_rendered_cards(self):
        make_card(name="BDE")
        response = self.client.post(reverse("open_pack"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["cards"]), 5)
        first = data["cards"][0]
        self.assertEqual((first["rarity"], first["slug"], first["is_new"]), (1, "common", True))
        self.assertIn("BDE", first["html"])
        self.assertIn('class="card rarity-common"', first["html"])
        self.assertTrue(data["next_pack_at"])

    def test_cards_owned_before_are_not_new(self):
        make_card()
        self.client.post(reverse("open_pack"))
        User.objects.update(next_pack_at=None)  # skip the cooldown
        data = self.client.post(reverse("open_pack")).json()
        self.assertFalse(any(c["is_new"] for c in data["cards"]))

    def test_open_twice_returns_409(self):
        make_card()
        self.client.post(reverse("open_pack"))
        response = self.client.post(reverse("open_pack"))
        self.assertEqual(response.status_code, 409)
        self.assertIn("error", response.json())
        self.assertTrue(response.json()["next_pack_at"])
        self.assertEqual(Pull.objects.count(), 5)

    def test_open_pack_rejects_get(self):
        self.assertEqual(self.client.get(reverse("open_pack")).status_code, 405)

    def test_card_html_is_escaped(self):
        make_card(name="<script>alert(1)</script>")
        html = self.client.post(reverse("open_pack")).json()["cards"][0]["html"]
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_collection_counts_only_my_copies(self):
        card = make_card(name="BDE")
        other = User.objects.create_user("gary", password="pw")
        now = timezone.now()
        Pull.objects.create(user=self.user, card=card, opened_at=now)
        Pull.objects.create(user=self.user, card=card, opened_at=now)
        Pull.objects.create(user=other, card=card, opened_at=now)
        make_card(name="Not mine")
        response = self.client.get(reverse("collection"))
        self.assertContains(response, "×2")
        self.assertNotContains(response, "Not mine")
        self.assertContains(response, "1 of 2 cards discovered")

    def test_home_loads_pack_opening(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, 'id="pack"')
        self.assertContains(response, "game/pack.js")
        self.assertContains(response, "game/fx.js")

    def test_card_detail_only_for_owned_cards(self):
        mine = make_card(name="BDE", description="Bienvenue au BDE")
        Pull.objects.create(user=self.user, card=mine, opened_at=timezone.now())
        Pull.objects.create(user=self.user, card=mine, opened_at=timezone.now())
        response = self.client.get(reverse("card_detail", args=[mine.pk]))
        self.assertContains(response, "Bienvenue au BDE")
        self.assertContains(response, "<dd>×2</dd>")
        other = make_card(name="Secret")
        self.assertEqual(self.client.get(reverse("card_detail", args=[other.pk])).status_code, 404)
