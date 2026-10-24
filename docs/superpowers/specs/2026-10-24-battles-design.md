# Battles — design

Date: 2026-10-24
Status: approved

## Intent

Give players something to *do* with their collection beyond opening packs and trading: a live,
best-of-5 stat duel against a friend, using a saved 5-card deck. Each round a random stat is drawn,
both players secretly commit a card, the higher value wins the round. Every player has a public
win/loss/draw record.

The fun is the decision each round: the stat is known before you pick, and each card can be played
only once per battle, so you choose between spending a strong card now or saving it.

## Goals

- Build and save one 5-card deck from your collection, seeing every card's stats while picking.
- Challenge a friend; both play live, at the same time.
- Fair simultaneous play: neither player can see the other's card before committing their own.
- W-L-D record per player.

## Non-goals

- No stakes: no cards are won or lost.
- No matchmaking with strangers, no bots — friends only (reuses `friends.are_friends`).
- No async/turn-by-mail play.
- No websockets/Channels: live updates are browser polling.
- No ranking/ELO.

## Anti-goals (would be a failure even if it "works")

- A player can learn the opponent's card before committing (via the UI, the JSON, or timing).
- A player who walks away freezes the battle forever for the other one.
- Two tabs / double-submits can play two cards in one round or the same card twice.

## Rules (decided with the user)

**Deck**
- Exactly 5 cards, each one the player owns (has a `Pull` of). Distinct cards (*my call*: owning
  2 copies doesn't let you play the same card twice).
- Rarity cap: at most 1 Legendary and at most 2 Epic.
- Deck selection screen shows all stats of each card: subscribers, posts, events. Cards are shown
  like the collection page (reuse `game/_card.html`).
- One saved deck per player, editable any time.

**Battle**
- Stats in play: `subscriber_count`, `post_count`, `event_count` (*my call*: rarity is not a stat).
- Each round: server draws a stat uniformly at random (repeats allowed). Both players pick one of
  their not-yet-played deck cards, secretly. When both have picked, both cards are revealed.
- Higher value wins the round; equal values = drawn round (no point).
- Max 5 rounds. The battle ends early as soon as the trailing player can no longer win **or draw**:
  i.e. when `abs(score_a - score_b) > rounds_remaining`.
- Equal score at the end = drawn battle.
- Turn timer: 30 s per pick (*my call*). If a player hasn't picked when it expires, a random one of
  their remaining cards is played for them.

**Record**
- Each player has W-L-D, shown on their own battle page and next to friends in the friends list
  (*my call* on placement).

## Flow

1. Player A opens a friend and clicks "Challenge" (needs a valid saved deck).
2. B sees the pending challenge (friends page / battle page, refreshed by polling) and accepts or
   declines. B also needs a valid saved deck to accept.
3. On accept, the battle starts: both decks are **snapshotted** at that moment (later deck edits or
   trades don't affect a running battle — *my call*).
4. Both players are on the battle page, which polls the server every 1–2 s for state and posts picks.
5. After the final round, the result is shown and both records update.

*My calls* on edges:
- A pending challenge expires after 2 minutes unaccepted (it's a live mode; stale challenges are noise).
- A player can be in at most one pending-or-running battle at a time, **incoming challenges
  included**: challenging someone who already has a pending (sent or received) or running battle
  fails with a "busy" message. With the 2-minute expiry this rarely bites, and it keeps one simple
  rule per player instead of cancelling competing challenges on accept.
- A saved deck can silently become invalid (a card traded away, or a re-import re-ranking a card's
  rarity past the cap). It is re-checked when sending and when accepting a challenge, and the player
  is told to fix it. The trade code is **not** touched.
- A posted pick is final. The snapshot freezes card stat values too.
- After both cards are revealed, there is a short pause before the next round's 30 s timer starts
  (length left to the builder). Any overdue rounds are caught up on the next read.
- The opponent's "has picked" status is shown (it reveals no card).
- Unfriending doesn't cancel a running battle.
- Abandonment needs no special handling: the 30 s auto-pick plays the absent player's cards and the
  battle finishes in ≤ 2.5 min.

## Technical constraints / decisions

- Django only, no new dependency. Plain JS in `game/static/game/`, like `pack.js`.
- Server is the sole authority: it draws stats, enforces the timer, resolves rounds. The client
  only displays state and posts picks.
- The state JSON sent to a player must never include the opponent's pick for the current round
  until both picks are in.
- **Opponent's deck is hidden** (decided with the user): a player sees an opponent card only once it
  has been revealed in a round. The state JSON must never contain the opponent's unplayed cards
  (ids, stats or markup) — only already-revealed ones, plus a count of cards remaining.
- Timer enforcement is lazy: no background worker. Whenever state is read or a pick is posted and
  the current round's deadline has passed, the server auto-picks for whoever hasn't picked, resolves
  the round, then returns state. Since both clients poll, this always happens within ~2 s.
- Concurrency: posting a pick and the lazy timeout must be safe under double-submit and two
  simultaneous polls — lock the battle row (`select_for_update`, as `accept_trade` does) while
  mutating.
- Follow existing structure: game logic in a module like `game/battles.py` (mirroring `trades.py` /
  `friends.py` with a `BattleError` for user-facing messages), thin views, tests in
  `game/tests/test_battles.py`.
- i18n: every new UI string wrapped and translated in `game/locale/fr/LC_MESSAGES/django.po` + `.mo`
  (see CLAUDE.md). JS strings go through `data-msg-*` attributes as in `pack.js`.

## Left to the builder

- Data model (deck storage, battle/round tables, whether W-L-D is stored or computed from finished
  battles).
- URL names, page layout, reveal animation.
- Exact polling interval within 1–2 s.
