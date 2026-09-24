from django.conf import settings
from django.test import TestCase
from django.urls import reverse


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
