# `komi_pages_dump.json` — data reference

## Top level

```json
{
  "clubs":   [ <page record>, ... ],
  "members": [ <page record>, ... ]
}
```

`clubs` = Komi "Clubs" (`page.type == "page"`). `members` = Komi "Membres"
(`page.type == "user"`). Both arrays hold the same record shape — a club and a
member are both just a `page` row underneath, only `type` differs.

## Page record shape

Each entry is: the search-result fields (flat, top level) **merged with**
`metadata`, `blocks`, and `_local_images` (added by the scraper).

```json
{
  "id": "3ce8b812-6527-4668-8e86-5c3709de280a",
  "name": "BDE",
  "type": "page",
  "logo_url": "https://komi.fra1.cdn.digitaloceanspaces.com/...",
  "banner_url": "https://komi.fra1.digitaloceanspaces.com/...",
  "is_public": true,

  "user_id": "032a5a54-...",  // members only — the auth user_id behind this page

  "metadata": { ... },        // full detail, see below
  "blocks": [ ... ] | null,   // presentation content blocks, see below
  "_local_images": { "<original url>": "images/<id>/<filename>", ... }
}
```

- **`id`** is the *page id* — the key used everywhere else (`page_id_input` /
  `p_page_id` in the API). It's what links a club/member to its posts,
  events, etc. in the rest of the Komi data model.
- **`user_id`** only appears on `members` entries — it's the Supabase
  `auth.users` id of the person, distinct from their page id.
- `logo_url` / `banner_url` here are the *search-result-time* image URLs;
  `metadata.logo` / `metadata.banner` (below) are the authoritative,
  richer versions of the same images.

### `metadata` (from `get_page_metadata`)

```json
{
  "id": "<page id>",
  "logo":   { "id", "url", "width", "height", "blurhash", "file_name", "file_size", "file_type", "storage_key", "media_variant" } | null,
  "banner": { same shape as logo } | null,
  "page": {
    "name": "BDE",
    "type": "page" | "user",
    "description": "Cercle des élèves ⭕️",   // the "presentation" text
    "color": "ff02b2fd",
    "primary_color": "#b80c09",
    "secondary_color": "#6a040f",
    "admin_id": "<user id of the page's admin>",
    "owner_id": "<user id of the page's owner, may be null>",
    "circle_id": "<school circle id — same for every record in this dump>",
    "parent_page_id": null,
    "is_public": true,
    "is_validated": true,
    "is_referenced": true,
    "is_team_visible": true,
    "primary_locale": "fr",
    "page_access_mode": "tags" | "subscription" | ...
  },
  "events": [ ... ],          // upcoming events tied to this page
  "shotguns": [ ... ],        // ticketed events ("shotguns") tied to this page
  "can_view": true,
  "is_member": false,
  "is_subscribed": false,
  "is_discoverable": true,
  "is_boutique_open": false,
  "post_count": 12,
  "event_count": 3,
  "subscriber_count": 214,
  "access_reason": "..."
}
```

`metadata` is `null` if that call failed for this page (see **Failures**
below) — otherwise every field above should be present, though `logo`/
`banner`/lists can themselves be `null`/empty.

### `blocks` (from `get_page_blocks`)

The `bloc_list` array of the page's "presentation" tab — the rich content
blocks shown on the page itself (text, images, links, etc., in display
order). `null` if the call failed (e.g. private page you don't have access
to) rather than an empty page — check for `null` vs `[]` to tell "no
presentation content" apart from "couldn't fetch it". The scraper doesn't
interpret block contents — each entry is passed through as-is from the API.

### `_local_images`

Every image URL the scraper found anywhere inside this record (logo, banner,
plus any image URLs nested inside `blocks`), mapped to where it was saved
locally:

```json
"_local_images": {
  "https://komi.fra1.cdn.digitaloceanspaces.com/v2/.../master.webp": "images/3ce8b812-6527-4668-8e86-5c3709de280a/master.webp",
  "https://komi.fra1.digitaloceanspaces.com/.../banner.jpg": "images/3ce8b812-6527-4668-8e86-5c3709de280a/banner.jpg"
}
```

Paths are relative to the directory the scraper was run from. To resolve any
image URL you find in a record (`logo.url`, `banner.url`, a URL inside
`blocks`, or the top-level `logo_url`/`banner_url`), look it up as a key in
that record's `_local_images` — if present, that's the on-disk copy; if
absent, it wasn't downloaded (e.g. added to the record after the scraper ran,
or the download itself failed).

## `images/` directory layout

```
images/
  <page id>/
    <original filename>
    <original filename>
    ...
```

One subfolder per page id (club or member, same id as `record["id"]`), named
files kept as-is from the URL (so a club and a member never collide, and
re-running the scraper skips files that already exist on disk rather than
re-downloading).

## Failures

Scraping ~2100 pages hits some you don't have permission to see (private
pages, subscription-only, etc. → HTTP 403). The scraper doesn't abort on
these — it logs a warning and leaves `metadata` and/or `blocks` as `null` for
that record. Any code built on this dump should treat `null` there as "not
accessible", not "doesn't exist".


