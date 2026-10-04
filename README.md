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

| Tool | What it does |
|---|---|
| `Matter.GetAccount` | The connected Matter account and its API rate limits |

The rest of the catalog lands in phases (see [docs/SPEC.md](docs/SPEC.md#tool-catalog)).
Every tool is tagged read-only or write (and delete tools as destructive), so a gateway can
expose only the read tools.

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

Then add the server's tools to an MCP Gateway in the Arcade dashboard (Arcade Auth mode)
and connect a client, for example `arcade connect claude-code --gateway <slug>`.

## Security

Never commit tokens or personal library data. Tests use invented data only. The token is
held by Arcade and injected per request; it is never exposed to the model.

## License

[MIT](LICENSE)
