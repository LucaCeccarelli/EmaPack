from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from game.models import User


class I18nInfrastructureTests(TestCase):
    def test_locale_middleware_is_installed_between_session_and_common(self):
        session_index = settings.MIDDLEWARE.index("django.contrib.sessions.middleware.SessionMiddleware")
        locale_index = settings.MIDDLEWARE.index("django.middleware.locale.LocaleMiddleware")
        common_index = settings.MIDDLEWARE.index("django.middleware.common.CommonMiddleware")
        self.assertTrue(session_index < locale_index < common_index)

    def test_french_is_an_available_language(self):
        self.assertIn(("fr", "Français"), settings.LANGUAGES)

    def test_set_language_view_sets_cookie_and_redirects(self):
        response = self.client.post(reverse("set_language"), {"language": "fr", "next": "/"})
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertEqual(self.client.cookies[settings.LANGUAGE_COOKIE_NAME].value, "fr")


class LanguageSwitcherTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ash", password="pw")
        self.client.force_login(self.user)

    def test_switcher_posts_to_set_language_with_both_options(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, f'action="{reverse("set_language")}"')
        self.assertContains(response, 'name="language" value="fr"')
        self.assertContains(response, 'name="language" value="en"')

    def test_english_is_marked_active_by_default(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, 'value="en" class="active"')

    def test_switcher_is_visible_when_logged_out(self):
        self.client.logout()
        response = self.client.get(reverse("login"))
        self.assertContains(response, f'action="{reverse("set_language")}"')


class PackDataAttributesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ash", password="pw")
        self.client.force_login(self.user)

    def test_stage_exposes_translatable_pack_messages(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, 'data-msg-ready="A pack is ready!"')
        self.assertContains(response, 'data-msg-next-in="Next pack in {mm}:{ss}"')
        self.assertContains(response, 'data-msg-session-expired="Your session expired. Please log in again."')
        self.assertContains(response, 'data-msg-generic-error="Something went wrong. Try again."')
        self.assertContains(response, 'data-msg-open-failed="Could not open the pack. Try again."')
        self.assertContains(response, 'data-msg-tap-to-reveal="Tap to reveal"')
        self.assertContains(response, 'data-msg-swipe-next="Swipe it away, or tap for the next card"')
        self.assertContains(response, 'data-msg-new-badge="NEW!"')
