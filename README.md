# arcade-matter-mcp

An MCP server for [Matter](https://getmatter.com), the read-later app, built with
[arcade-mcp](https://github.com/ArcadeAI/arcade-mcp), hosted on Arcade Cloud via
`arcade deploy`, and used through Arcade MCP Gateways.

It wraps Matter's [public API](https://docs.getmatter.com/api) so agents can search your
library, read articles and highlights, save links, and organize your queue. See
[docs/SPEC.md](docs/SPEC.md) for the full design.

> **Single user.** Matter only offers personal API tokens (no OAuth), and Arcade secrets
> are shared across a project. Everyone who can call this server acts on the token
> owner's library, so keep its gateway to yourself.

## Tools

Phase 1 (read-only):

| Tool | What it does |
|---|---|
| `Matter.GetAccount` | The connected Matter account and its API rate limits |
| `Matter.ListItems` | Items in the queue, inbox or archive, filtered by favorite, tag, type or date |
| `Matter.GetItem` | One item's metadata |
| `Matter.GetItemContent` | An item's full text as Markdown, in bounded chunks |
| `Matter.SearchLibrary` | Full-text search with `"phrase"`, `-term`, `by:`, `site:` and `title:` |
| `Matter.ListHighlights` | Highlights and notes on one item |
| `Matter.ListTags` | Tags and how many items each is on |
| `Matter.ListReadingSessions` | Reading sessions with start time and duration |

Phase 2 (writes):

| Tool | What it does |
|---|---|
| `Matter.SaveItem` | Save a public URL to the queue or archive (have your client [approve each URL](docs/security/save-item-urls.md)) |
| `Matter.UpdateItem` | Archive or re-queue, favorite, or set reading progress |
| `Matter.AddTag` / `Matter.RemoveTag` | Tag or untag an item (tags are created by name) |
| `Matter.RenameTag` | Rename a tag everywhere |
| `Matter.SetHighlightNote` | Add, change or clear a highlight's note |
| `Matter.DeleteItem` / `Matter.DeleteHighlight` / `Matter.DeleteTag` | Permanent deletes (destructive) |

Phase 3 (summaries, read-only):

| Tool | What it does |
|---|---|
| `Matter.GetItemWithHighlights` | An item with all its highlights and notes |
| `Matter.ListRecentHighlights` | Highlights made or edited recently, grouped by item |
| `Matter.SummarizeReadingTime` | Reading time totals, averages, streaks and busiest day for a period |

Every tool is tagged read-only or write (and delete tools as destructive), so a gateway can
expose only the read tools. The server can't enforce approval for writes itself, so use a
read-only gateway day to day and a separate, approval-gated one for writes (see
[Deploy](#deploy)).

## Setup

1. Get a Matter API token (needs Matter Pro) at
   [web.getmatter.com/settings](https://web.getmatter.com/settings) → **Generate API
   Token**. Generating a token revokes any previous one, so reuse an existing token if
   another tool (such as `matter-cli`) already has it.
2. `cp .env.example .env` and set `MATTER_API_TOKEN`.

## Development

```bash
uv tool install arcade-mcp      # Arcade CLI
uv sync --extra dev             # project and dev dependencies
uv run pytest                   # unit tests (Matter is mocked; no network)
uv run ruff check . && uv run ruff format --check . && uv run mypy src
```

Tool-selection evals (need an LLM API key; they don't call Matter):

```bash
ANTHROPIC_API_KEY=... uv run arcade evals evals/ -p anthropic
```

To try the tools against your own library locally, run the server over stdio (Arcade's
local HTTP transport doesn't serve tools that need secrets):

```bash
uv run src/arcade_matter/server.py                     # stdio
(cd src/arcade_matter && arcade configure claude -n matter)   # add it to Claude Desktop
```

## Deploy

```bash
arcade login
arcade deploy -e src/arcade_matter/server.py    # uploads MATTER_API_TOKEN from .env
```

Rotate the token later without redeploying:

```bash
arcade secret set MATTER_API_TOKEN=mat_...
```

Then create two MCP Gateways in the Arcade dashboard, both in Arcade Auth mode:

- a **read-only gateway** with only the read tools, for everyday use;
- a **write-only gateway** with the write tools you want (and the delete tools only if you
  need them), connected only through a client that asks you to approve every call to it.
  That client also connects the read-only gateway to look up IDs.

Connect a client with, for example, `arcade connect claude-code --gateway <slug>`. See
[docs/security/gateways.md](docs/security/gateways.md) for the tool lists, client
settings and how to check the read connection can't change anything.

## Security

Never commit tokens or personal library data. Tests use invented data only. The token is
held by Arcade and injected per request; it is never exposed to the model.

Asking the model to confirm before a write is advice, not a safeguard. The safeguards are
the read-only gateway and client-enforced approval for writes; see
[docs/security/](docs/security/).

## License

[MIT](LICENSE)
