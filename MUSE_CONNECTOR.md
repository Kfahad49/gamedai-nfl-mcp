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
| Access requirements | No account needed. No regional limits. Backend errors return structured `code` / `http_status` / `message` objects, never stack traces. Scout tools may return `tier: public_degraded` when the backend is serving public-tier data; this is a backend state, not a client auth failure. |

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

## Pre-submission verification (2026-09-27)

Exercised end to end with a raw streamable HTTP client, no credentials:

- `initialize` negotiated protocol 2025-03-26, server `Scout by gamedai 1.28.1`.
- `get_game_scores` returned the live Sunday slate with in-progress clocks.
- `get_wire_news(page_size=3)` returned three current articles with sources.
- `get_player_grade("Josh Allen")` returned an A+ with nflverse attribution.
- `get_start_sit_recommendation` and `get_scout_rankings` returned
  `tier: public_degraded`. That value is a hardcoded literal on both backend
  routes (`backend/app/routers/scout.py`). It is the name of the free public
  tier, it is the only tier those routes can return, and it has nothing to do
  with API keys. The preview backend has no Scout keys configured, so a
  missing or invalid key changes nothing there.
- The null start/sit recommendation for a 2026 week was a bug, now fixed on
  the backend side: projection rows for the current season existed with no
  points, and two nulls compared as a 0.0 to 0.0 tie labelled `grounded`.
  The backend now reports that as ungrounded and names the player with no
  Sleeper projection for that week. Real ties still return `grounded: true`.
- Start/sit is only as fresh as the last manual run of
  `backend/scripts/backfill_sleeper_projections.py`; there is no scheduled
  refresh. Run it for the current week before Meta's end-to-end test.
- Rankings come live from FantasyPros for the current calendar-year season;
  `week` omitted means FantasyPros' current week, and an out-of-range week
  returns an empty list rather than stale rows.
- Player grades cite `stats_season` (2025) and nflverse attribution in every
  response; that is the latest complete stats season, not the live one.
- This server now defaults start/sit to the current NFL season and echoes
  `season` and `week` on start/sit and `week` on rankings, so an agent can
  say which week an answer is for. Before this, an omitted season meant 2025.

These checks prove the endpoint works for a generic MCP client. They do not
prove Muse itself has used the tools. That is only established by running the
custom-integration prompt above inside Muse, or by Meta's end-to-end review.

No Scout key is ever sent to the MCP client. The same considerations in
`CHATGPT_APP.md` about key enforcement and `/readyz` apply here.
