# Pack Ema

A trading card game for IMT Alès: every club and student page from Komi becomes a card.
Sign up, open a pack of 5 cards every 10 minutes, and build your collection.

## What you need

- [Docker](https://docs.docker.com/get-docker/) with Compose — or [uv](https://docs.astral.sh/uv/) to run without Docker
- The scraped data at the root of the project (not in git):
  - `komi_pages_dump.json` — the dump
  - `images/` — the downloaded pictures (`images/<page id>/<file>`)

## Launch

```bash
docker compose up --build
```

Open http://localhost:8000 and sign up. This starts two containers: the app (`web`) and PostgreSQL 17 (`db`).
The database is stored in the Docker volume `pgdata`, so it survives restarts; `docker compose down -v` wipes it.

Change the time between packs with `PACK_COOLDOWN_SECONDS` (default `600` = 10 min), handy for testing:

```bash
PACK_COOLDOWN_SECONDS=10 docker compose up
```

## Import the dump

With the app running, in another terminal:

```bash
docker compose exec web python manage.py import_komi komi_pages_dump.json
```

It prints something like `Imported 2103 cards. Rarities: {'Common': 1578, ...}`.

- **Safe to re-run** with a newer dump: existing cards are updated in place, players keep their collections.
- **Rarity** comes from `subscriber_count`: cards are ranked against every card in the database — top 1% Legendary, next 4% Epic, next 10% Rare, next 25% Uncommon, the rest Common. Tweak `RARITY_THRESHOLDS` in `game/management/commands/import_komi.py` and re-run the import to change it.
- Card fields: name, short description, presentation text (from the page's `blocks`), logo, banner, colors, subscriber/post/event counts. Data format: see `KOMI_DUMP_SCHEMA.md`.

## Player-proposed cards

Players can design a new card on **Propose** (http://localhost:8000/cards/propose/): name, tagline, description, logo, banner and colors, with a live preview. Each player can have up to 3 proposals waiting for review; images must be real images, 5 MB max (`PROPOSAL_MAX_IMAGE_BYTES`), stored in `images/proposals/`.

Admins review them in **Admin → Proposed cards**: pick the rarity in the list, **Save**, then select the cards and run **Approve** (they can now be pulled from packs) or **Reject**. Only approved cards ever appear in packs, and re-running the import never changes a proposed card's rarity.

## Admin (optional)

```bash
docker compose exec web python manage.py createsuperuser
```

Then browse cards and players at http://localhost:8000/admin/.

## Without Docker

The app still needs PostgreSQL. The easiest is to run only the database container (it listens on `localhost:5432`, user/password/db `pack_ema`):

```bash
docker compose up -d db
uv sync
uv run python manage.py migrate
uv run python manage.py import_komi komi_pages_dump.json
uv run python manage.py runserver        # PACK_COOLDOWN_SECONDS=10 works here too
```

To use another PostgreSQL server, set `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER` and `POSTGRES_PASSWORD`.
If port 5432 is already taken on your machine, start with `POSTGRES_PORT=5433 docker compose up` and use the same variable for `uv run`.

## Tests

Tests run against PostgreSQL too (Django creates a temporary `test_pack_ema` database):

```bash
docker compose exec web python manage.py test game   # or: uv run python manage.py test game
```

> Development setup only (`DEBUG=True`, Django dev server, images served by Django). Don't expose it to the internet as is.
