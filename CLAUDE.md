# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Pack Ema: a trading card game for IMT Alès. Every club and student page scraped from Komi becomes a
collectible card. Players sign up, open a pack of 5 cards every `PACK_COOLDOWN_SECONDS` (default 600s),
and build a collection. Players can also propose their own cards for admin approval. Single Django app
(`game`) in project `tcg`.

## Commands

Run everything through Docker Compose (`web` = Django app, `db` = Postgres 17):

```bash
docker compose up --build                              # start app + db (http://localhost:8000)
PACK_COOLDOWN_SECONDS=10 docker compose up              # short cooldown for manual testing
docker compose exec web python manage.py <command>      # run any manage.py command
docker compose exec web python manage.py import_komi komi_pages_dump.json   # (re-)import cards
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py test game                          # full test suite
docker compose exec web python manage.py test game.tests.test_packs         # one test module
docker compose exec web python manage.py test game.tests.test_packs.PackTests.test_open_pack  # one test
```

Without Docker (needs `uv`, and Postgres reachable — `docker compose up -d db` gives you that on
`localhost:5432`):

```bash
uv sync
uv run python manage.py migrate
uv run python manage.py runserver          # PACK_COOLDOWN_SECONDS=10 works here too
uv run python manage.py test game
```

Tests run against a real Postgres (Django spins up a temporary `test_pack_ema` database) — there is no
sqlite fallback, so `db` (or an equivalent `POSTGRES_HOST`) must be reachable to run tests.

There is no configured linter/formatter or JS build step — `game/static/game/*.js` and `*.css` are plain
files served as-is by `django.contrib.staticfiles`.

## Data dependency: the Komi dump

The app is driven by data that is **not in git**: `komi_pages_dump.json` and `images/` at the project
root (scraped separately). `game/management/commands/import_komi.py` reads the dump and upserts `Card`
rows keyed by `komi_id`; re-running it after a fresh dump updates existing cards without touching player
collections (`Pull`s) or proposed cards. See `KOMI_DUMP_SCHEMA.md` for the exact JSON shape (`clubs` /
`members` arrays, `metadata`, `blocks`, `_local_images`) — read it before touching import logic, since
several fields can legitimately be `null` (scrape failures) vs. empty (no content), and that distinction
matters.

Rarity for imported cards is **rank-based**, not absolute: `assign_rarities()` in `import_komi.py` sorts
all imported cards by `subscriber_count` and buckets them by percentile (`RARITY_THRESHOLDS`: top 1%
Legendary, next 4% Epic, next 10% Rare, next 25% Uncommon, rest Common). This re-ranks the *entire* card
table on every import — but only cards with `komi_id` set; player-proposed cards keep whatever rarity the
admin assigned and are never touched by import.

## Card lifecycle: two origins, one model

`Card` rows come from two different paths but share one table and one `status` field
(`pending` / `approved` / `rejected`):

- **Imported** (`komi_id` set): created by `import_komi`, `status` always `approved`.
- **Proposed** (`komi_id` null, `proposed_by`/`proposed_at` set): created via `views.propose_card`
  (`/cards/propose/`), starts `pending`. `CardProposal` in `models.py` is a **proxy model** over `Card`
  used only to give admins a separate "Proposed cards" list in `/admin/` (`game/admin.py`); it's the same
  table, not a separate one.

Only `status=approved` cards are ever eligible to drop from a pack (`game/packs.py` filters on this).
Admins review pending proposals in the `CardProposalAdmin` list view: pick the rarity inline
(`list_editable`), then run the `approve` / `reject` admin actions. A player may have at most
`MAX_PENDING_PROPOSALS` (3, in `views.py`) proposals awaiting review at once.

## Pack opening (`game/packs.py`)

`open_pack(user)` is the core game mechanic and its concurrency-safety is the main thing to preserve if
touched:

- The cooldown claim is a **conditional `UPDATE`** (`User.objects.filter(...).update(...)`) used as a
  lock — its return value (rows affected) is what prevents two simultaneous requests from both claiming
  the same pack, not a `select_for_update` or application-level lock.
- A pack is 5 slots: 4 drawn from `SLOT_ODDS`, the last ("the hit") always drawn from `HIT_ODDS`
  (guaranteed Rare or better) — see `pick_rarity()`. Odds are relative weights per rarity, restricted to
  rarities that actually have at least one approved card.
  - Card selection within a rarity is `order_by("?").first()` — fine at the current ~2k-card scale; the
    comment in the code flags this as the thing to precompute if the card pool grows significantly.
- Every pulled card becomes a `Pull` row (one per card, not one per pack) sharing the same `opened_at`
  timestamp — that shared timestamp is what groups 5 `Pull`s into "a pack" when querying history.

## Request flow for opening a pack

`views.open_pack_view` (`POST /packs/open/`) is a JSON endpoint used by `game/static/game/pack.js` for the
pack-opening animation: it returns `next_pack_at` plus each card's rarity/slug/`is_new` flag and
pre-rendered HTML (`game/_card.html` partial via `render_to_string`), so the frontend never re-implements
card markup. `PackUnavailable` (cooldown not elapsed, or no approved cards exist) maps to HTTP 409 with
the real `next_pack_at` re-fetched from the DB, so the client can resync its timer even if it was out of
sync.

## Auth & user model

`game.User` (`AUTH_USER_MODEL`) extends `AbstractUser` with just `next_pack_at` (nullable — `None` means
"never opened a pack," so a new signup can open one immediately). Signup/login/logout are Django's stock
views wired in `tcg/urls.py`; `SignupForm` is `UserCreationForm` swapped to the custom model.

## Images

`MEDIA_ROOT` is `images/` at the project root (the same directory the Komi scraper writes into) —
imported cards' `logo`/`banner` paths point into the scraper's `images/<page id>/...` layout, while
player-proposed uploads are namespaced under `images/proposals/` (`upload_to="proposals/"` on the model
fields). In dev, Django serves `MEDIA_URL` directly (`static()` helper in `tcg/urls.py`, active only
because `DEBUG=True`) — this setup is explicitly dev-only, not meant to be exposed as-is.

## Known constraints (intentional, don't "fix" without checking with the user)

- `DEBUG = True` and a hardcoded `SECRET_KEY` in `tcg/settings.py` — README explicitly flags this as
  development-only.
- Card selection in `open_pack` uses `order_by("?")`; acceptable at current data volume per the inline
  comment, not an oversight.
