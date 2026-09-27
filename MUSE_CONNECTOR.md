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
- `get_start_sit_recommendation` and `get_scout_rankings` returned valid data
  at `tier: public_degraded`. That field is set by the backend, and the
  preview backend returns the same tier with no key and with an invalid key,
  so the cause is on the backend side, not a missing MCP-side key. Check the
  backend's Scout tier logic before Meta's end-to-end test if full-tier output
  is wanted in the directory listing.

These checks prove the endpoint works for a generic MCP client. They do not
prove Muse itself has used the tools. That is only established by running the
custom-integration prompt above inside Muse, or by Meta's end-to-end review.

No Scout key is ever sent to the MCP client. The same considerations in
`CHATGPT_APP.md` about key enforcement and `/readyz` apply here.
