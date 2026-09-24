# French/English language switch — design

Date: 2026-09-24
Status: approved

## Goal

Let players switch the site's UI between French and English. Card content scraped
from Komi (club/member names, descriptions) is **not** translated — only the app's
own UI strings (nav, buttons, flash messages, form errors, pack-opening copy).

## Mechanism

- Add `django.middleware.locale.LocaleMiddleware` to `MIDDLEWARE` in `tcg/settings.py`,
  positioned right after `SessionMiddleware` and before `CommonMiddleware` (Django's
  required position for locale detection to see the session/cookie before routing).
- `LANGUAGES = [('en', 'English'), ('fr', 'Français')]`; `LANGUAGE_CODE` stays `en-us`
  as the ultimate fallback.
- No URL prefixing (`i18n_patterns` not used) — existing routes (`/collection/`,
  `/packs/open/`, etc.) are unchanged, so `pack.js`'s fetch to `stage.dataset.openUrl`
  needs no changes.
- Language resolution order (standard Django `LocaleMiddleware` behavior, no custom
  code): explicit user choice stored in session/cookie (`django_language`) takes
  priority; otherwise the browser's `Accept-Language` header is used if it matches
  `fr`; otherwise falls back to `LANGUAGE_CODE` (English).

## Switcher UI

- Small POST form in `base.html`'s header with two buttons/links (FR / EN), posting
  to Django's built-in `django.views.i18n.set_language` view (wired into
  `tcg/urls.py`). That view sets the session/cookie and redirects back to the
  `next` page (current URL, passed as a hidden field). No custom view or JS needed.

## Translated content

- **Templates** (`base.html` + the 9 templates under `game/templates/`): `{% load i18n %}`
  and wrap user-facing text in `{% trans %}` / `{% blocktrans %}`.
- **Python-side strings**: wrap with `gettext`/`gettext_lazy` (aliased `_`) in:
  - `game/views.py` — `messages.success`/`messages.error` calls, `forms.ValidationError` messages.
  - `game/friends.py` — `FriendError` messages.
  - `game/packs.py` — `PackUnavailable` messages.
  - `game/models.py` — `Rarity` (`IntegerChoices`) labels (`"Common"`, `"Uncommon"`,
    `"Rare"`, `"Epic"`, `"Legendary"`) wrapped in `gettext_lazy` (must be `_lazy`,
    not `gettext`, since choices are evaluated at import time). This is a *label*
    translation, not a data migration — `get_rarity_display()` picks it up
    automatically everywhere it's already called (`_card.html`, `card_detail.html`,
    `collection.html`, `propose.html`'s pending-proposals list, and the rarity
    radio-select rendered from `Rarity.choices` in `views.py`'s proposal form).
- **`game/static/game/pack.js`**: has ~4 hardcoded English strings (`"Tap to reveal"`,
  `"Swipe it away, or tap for the next card"`, `"A pack is ready!"`, the
  `"Next pack in {mm}:{ss}"` template, and the two network-error fallback strings).
  No `JavaScriptCatalog` — instead render these as `data-*` attributes on `#stage` in
  `home.html` (already carries `data-open-url`/`data-next-pack-at`), translated
  server-side via `{% trans %}`, and have `pack.js` read from `dataset` instead of
  literals.
- **`propose.js`** / `fx.js`: no user-facing copy found (`"Your card"` is a form
  placeholder default for an empty name field, not translated — cosmetic, low value).

## Translation files

- `LOCALE_PATHS = [BASE_DIR / "game" / "locale"]` in settings.
- `game/locale/fr/LC_MESSAGES/django.po` generated via
  `manage.py makemessages -l fr`, translated by hand, compiled via
  `manage.py compilemessages`.
- The `python:3.12-slim` base image has no `gettext` package (needed for
  `makemessages`/`compilemessages`); add `apt-get install -y gettext` to the
  `Dockerfile`.

## Out of scope

- Translating Komi-scraped card content (club names, descriptions, member bios).
- URL-based locale prefixes.
- A JS translation catalog for anything beyond the handful of `pack.js` strings.

## Testing

- No new dedicated i18n test — this is standard Django middleware/template-tag
  behavior, not new business logic.
- Existing `game.tests.*` suite must keep passing unchanged: since `LANGUAGE_CODE`
  stays `en-us` and tests don't set `Accept-Language`, any assertions on message
  text keep matching the English strings by default.
