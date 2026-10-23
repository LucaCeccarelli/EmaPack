# Graph Report - EmaPack  (2026-10-23)

## Corpus Check
- 42 files · ~33,881 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 9 file(s) not represented in the graph (top: (none) 3, .css 2, .example 1)

## Summary
- 444 nodes · 901 edges · 25 communities (15 shown, 10 thin omitted)
- Extraction: 81% EXTRACTED · 19% INFERRED · 0% AMBIGUOUS · INFERRED: 169 edges (avg confidence: 0.95)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `909b93a3`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- send_request
- Card
- User
- test_import.py
- admin.py
- open_pack
- ProposePageTests
- GameViewTests
- pack.js
- FrenchRenderingTests
- settings.py
- fx.js
- ProposalForm
- Pack Ema
- `komi_pages_dump.json` — data reference
- French/English language switch — design
- apps.py
- pack-ema

## God Nodes (most connected - your core abstractions)
1. `Card` - 46 edges
2. `User` - 40 edges
3. `Rarity` - 36 edges
4. `send_request()` - 29 edges
5. `open_pack()` - 25 edges
6. `ProposePageTests` - 23 edges
7. `Pull` - 22 edges
8. `GameViewTests` - 20 edges
9. `Friendship` - 19 edges
10. `FriendLogicTests` - 19 edges

## Surprising Connections (you probably didn't know these)
- `Translations (i18n)` --references--> `Rarity`  [INFERRED]
  CLAUDE.md → game/models.py
- `Task 6: Python-side user-facing strings translated` --references--> `FriendError`  [INFERRED]
  docs/superpowers/plans/2026-09-24-i18n-fr-en.md → game/friends.py
- `Task 6: Python-side user-facing strings translated` --references--> `remove_friendship()`  [INFERRED]
  docs/superpowers/plans/2026-09-24-i18n-fr-en.md → game/friends.py
- `Auth & user model` --references--> `User`  [INFERRED]
  CLAUDE.md → game/models.py
- `Task 4: Accounts, pages and the card face` --references--> `User`  [INFERRED]
  docs/superpowers/plans/2026-09-23-komi-tcg.md → game/models.py

## Import Cycles
- None detected.

## Communities (25 total, 10 thin omitted)

### Community 0 - "send_request"
Cohesion: 0.06
Nodes (15): Translated content, accept_request(), are_friends(), FriendError, friends_of(), remove_friendship(), send_request(), Friendship (+7 more)

### Community 1 - "Card"
Cohesion: 0.07
Nodes (27): Auth & user model, Request flow for opening a pack, File Structure, Task 1: Project scaffold and models, Task 2: `import_komi` management command, Task 4: Accounts, pages and the card face, Task 5: Effects toolkit (`fx.js`): holo tilt, particles, flash, shake, sound, Task 6: Python-side user-facing strings translated (+19 more)

### Community 2 - "User"
Cohesion: 0.08
Nodes (15): Deliberately out of scope (add when needed), Facts about the real dump (measured, drive design decisions), Global Constraints, Komi TCG Implementation Plan, Task 3: Pack opening logic, Migration, Migration, Migration (+7 more)

### Community 3 - "test_import.py"
Cohesion: 0.09
Nodes (11): Data dependency: the Komi dump, assign_rarities(), blocks_to_text(), card_fields(), color(), Command, local_image(), rarity_for() (+3 more)

### Community 4 - "admin.py"
Cohesion: 0.08
Nodes (17): Card lifecycle: two origins, one model, Task 3: Rarity & status labels translated, CardAdmin, CardProposalAdmin, thumb(), CardProposal, Meta, background_color (+9 more)

### Community 5 - "open_pack"
Cohesion: 0.11
Nodes (13): Commands, Configuration (`.env`), Images, Known constraints (intentional, don't "fix" without checking with the user), Pack opening (`game/packs.py`), Translations (i18n), What this is, Review Focus (+5 more)

### Community 6 - "ProposePageTests"
Cohesion: 0.11
Nodes (5): make_card(), png(), ProposalLifecycleTests, ProposePageTests, valid_data()

### Community 7 - "GameViewTests"
Cohesion: 0.13
Nodes (5): Task 6: The pack opening sequence, AuthTests, GameViewTests, LeaderboardTests, make_card()

### Community 8 - "pack.js"
Cohesion: 0.16
Nodes (18): French/English Language Switch Implementation Plan, Global Constraints, Task 1: I18n routing & infrastructure, Task 2: Language switcher UI in the header, Task 4: Card & collection templates translated, Task 7: pack.js strings exposed via data attributes, Task 8: French translation catalog + end-to-end verification, buildStack() (+10 more)

### Community 9 - "FrenchRenderingTests"
Cohesion: 0.10
Nodes (4): FrenchRenderingTests, I18nInfrastructureTests, LanguageSwitcherTests, PackDataAttributesTests

### Community 11 - "fx.js"
Cohesion: 0.18
Nodes (4): burst(), init(), resize(), tick()

### Community 12 - "ProposalForm"
Cohesion: 0.25
Nodes (3): Task 5: Forms & social templates translated, ProposalForm, Meta

### Community 13 - "Pack Ema"
Cohesion: 0.20
Nodes (9): Admin (optional), Deploying, Import the dump, Launch, Pack Ema, Player-proposed cards, Tests, What you need (+1 more)

### Community 14 - "`komi_pages_dump.json` — data reference"
Cohesion: 0.22
Nodes (8): `blocks` (from `get_page_blocks`), Failures, `images/` directory layout, `komi_pages_dump.json` — data reference, `_local_images`, `metadata` (from `get_page_metadata`), Page record shape, Top level

### Community 15 - "French/English language switch — design"
Cohesion: 0.25
Nodes (7): French/English language switch — design, Goal, Mechanism, Out of scope, Switcher UI, Testing, Translation files

## Knowledge Gaps
- **1 isolated node(s):** `pack-ema`
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 185 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `User` connect `User` to `send_request`, `Card`, `test_import.py`, `admin.py`, `open_pack`, `ProposePageTests`, `GameViewTests`, `FrenchRenderingTests`?**
  _High betweenness centrality (0.179) - this node is a cross-community bridge._
- **Are the 29 inferred relationships involving `Card` (e.g. with `Card lifecycle: two origins, one model` and `Data dependency: the Komi dump`) actually correct?**
  _`Card` has 29 INFERRED edges - model-reasoned connections that need verification._
- **What connects `pack-ema` to the rest of the system?**
  _1 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `send_request` be split into smaller, more focused modules?**
  _Cohesion score 0.06077694235588972 - nodes in this community are weakly interconnected._
- **Why does `Rarity` connect `User` to `send_request`, `Card`, `test_import.py`, `open_pack`, `ProposePageTests`, `GameViewTests`, `pack.js`, `FrenchRenderingTests`, `ProposalForm`?**
  _High betweenness centrality (0.174) - this node is a cross-community bridge._
- **Are the 27 inferred relationships involving `User` (e.g. with `Auth & user model` and `Komi TCG Implementation Plan`) actually correct?**
  _`User` has 27 INFERRED edges - model-reasoned connections that need verification._
- **Should `Card` be split into smaller, more focused modules?**
  _Cohesion score 0.06918238993710692 - nodes in this community are weakly interconnected._