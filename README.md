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

Open http://localhost:8000 and sign up. The database (`db.sqlite3`) is created on first start and lives in the project folder, so it survives restarts.

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

## Admin (optional)

```bash
docker compose exec web python manage.py createsuperuser
```

Then browse cards and players at http://localhost:8000/admin/.

## Without Docker

```bash
uv sync
uv run python manage.py migrate
uv run python manage.py import_komi komi_pages_dump.json
uv run python manage.py runserver        # PACK_COOLDOWN_SECONDS=10 works here too
```

## Tests

```bash
uv run python manage.py test game
```

> Development setup only (`DEBUG=True`, Django dev server, images served by Django). Don't expose it to the internet as is.
