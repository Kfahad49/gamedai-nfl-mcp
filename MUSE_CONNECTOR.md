# Scout by gamedai, Meta Muse connection

Muse (muse.ai) has no downloadable connector SDK. There are two ways a Muse
agent reaches this server, and both use the same hosted MCP URL:

`https://gamedai-mcp.fly.dev/mcp`

Nothing is uploaded to Meta. Muse builds its bridge with the official MCP SDK
over streamable HTTP and calls the advertised tools directly.

## 1. Custom integration (works today, no review)

Any Muse user can connect gamedai with one message:

> Build a custom integration to gamedai. Its MCP server URL is
> https://gamedai-mcp.fly.dev/mcp. It gives me live NFL scores, Wire news,
> Scout player grades, start/sit calls, and fantasy rankings. No login needed.

Meta does not review custom integrations. Users trust the endpoint directly.

## 2. Directory connector (submitted at muse.ai/platform)

The form has three steps. These are the values to enter.

### Overview

| Field | Value |
| --- | --- |
| Connector name | Scout by gamedai |
| Company / developer | gamedai (omniviewai) |
| Product website | https://gamedai.app |
| Icon (512x512 PNG) | https://gamedai.app/icon.png |
| Accepts payments | No |
| Work email | hello@gamedai.app |
| Support | hello@gamedai.app |
| Privacy policy | https://gamedai.app/privacy |
| Terms of service | https://gamedai.app/terms |

Example prompts:

- "What's the score of the Bills game right now?"
- "Give me the latest NFL news from the Wire."
- "What's Josh Allen's Scout grade this season?"
- "Start Josh Allen or Lamar Jackson in week 4?"
- "Show me the top PPR running backs this week."

Description: Scout by gamedai gives agents read-only NFL intelligence. Live
game scores, the Wire news feed, Scout player grades, head-to-head start/sit
recommendations, and positional fantasy rankings. All tools are read-only and
non-destructive. Grades cite their data source and license in every response.

### Technical specs

| Field | Value |
| --- | --- |
| Connection type | Existing MCP |
| Hosted MCP endpoint | https://gamedai-mcp.fly.dev/mcp |
| Documentation | https://github.com/omniviewai/gamedai-nfl-mcp |
| Authentication | None. Public, unauthenticated. |
| Access requirements | No account needed. No regional limits. Backend errors return structured `code` / `http_status` / `message` objects, never stack traces. Scout tools return `tier: public_degraded`, the name of the free tier; it is the only tier these routes serve and is unrelated to auth. |

### Review

Confirm authorization to submit, acknowledge that submission does not
guarantee approval, and accept the Muse Connector Terms. Meta then runs
functional, security, and legal review plus end-to-end testing against the
live endpoint above.

## Tools advertised

- `get_game_scores(date?, event_id?)`
- `get_wire_news(page?, page_size?)`
- `get_player_grade(player, season?, week?)`
- `get_start_sit_recommendation(player_a, player_b, week, season?)`
- `get_scout_rankings(position?, scoring?, week?)`

All five carry `readOnlyHint: true` and `destructiveHint: false`. Season
defaulting follows the rule in `README.md`.

## Requested vs verified context in responses

An agent must not report a requested week as the week the data is for. The
responses keep the two apart:

- Start/sit: `requested_season` and `requested_week` are the query, added by
  this server. The backend does not report a source week; the projection row
  it read is for exactly that season and week or the answer is ungrounded.
- Rankings: `requested_week` is the query. `source_season`, `source_week`,
  and `source_status` come from the backend, which reads them from the
  FantasyPros body. Null means the body did not say; it is never copied from
  the request. `source_status` other than `ok` explains an empty list
  (`disabled`, `upstream_error`, `empty`, `rate_limited`).
- Player grade: `stats_season` and `attribution` say which completed season
  the grade was computed from and credit nflverse.

Fields that are null are unknown, not zero and not "current".

## Data freshness, verified 2026-09-27

- Start/sit projections are loaded by the manual
  `backend/scripts/backfill_sleeper_projections.py`; there is no scheduled
  refresh. A 2026 week is only as fresh as the last run for that week.
  Sleeper's free feed had usable PPR points for 2026 weeks 3, 4, and 5 when
  checked (about 1,000 players per week with points, Josh Allen included),
  so a run for the current week would load real numbers. Whether the
  production table already holds them was not checked; that needs DB access.
- Rankings are fetched live from FantasyPros for the current calendar-year
  season. An omitted week means the source's current week.
- A start/sit "tie" for a 2026 week with `grounded: true` was a bug:
  projection rows existed with null points and compared as 0.0 to 0.0. Fixed
  in the backend; a missing projection is now ungrounded and the rationale
  names the player without naming a feed, since the loader reads ESPN and
  Sleeper rows and cannot tell which one was empty.

## Verification status

Two kinds of checks, kept separate.

### Checks run from this repo (generic MCP client, not Muse)

Exercised end to end with a raw streamable HTTP client, no credentials, on
2026-09-27:

- `initialize` negotiated protocol 2025-03-26, server `Scout by gamedai 1.28.1`.
- `get_game_scores` returned the live Sunday slate with in-progress clocks.
- `get_wire_news(page_size=3)` returned three current articles with sources.
- `get_player_grade("Josh Allen")` returned an A+ with nflverse attribution.
- `get_scout_rankings(QB, PPR)` returned 50 rows; week 20 returned an empty
  list rather than stale rows.
- `get_start_sit_recommendation` returned the null "tie" described above for
  2026 weeks and real picks for 2025 week 4.

These prove the endpoint works for a generic MCP client. They do not prove
Muse used it.

### Checks run inside Muse

None recorded yet. No Muse session transcript or result has been provided to
this repo. When one is, record it here with the date, the prompt used, the
tool calls Muse made, and what it answered, so it is not confused with the
generic checks above.

No Scout key is ever sent to the MCP client. The same considerations in
`CHATGPT_APP.md` about key enforcement and `/readyz` apply here.
