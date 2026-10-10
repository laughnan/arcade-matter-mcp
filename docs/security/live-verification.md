# Verifying the live deployment

The source review can't see how the server is actually deployed. Because every caller acts
on the token owner's library, these checks confirm only the owner can reach the tools, and
that what runs is what was reviewed. Repeat them after changing gateways, project members
or dependencies, and at least every few months.

The dashboard checks in sections 1 and 2 are what limit who can act on the library. The
script in section 3 only shows that some anonymous requests are refused; a passing run
doesn't replace them.

Record the results in the table at the end. Never record the Matter token, the worker
secret, an Arcade API key or library contents.

## 1. Authentication and membership

In the Arcade dashboard:

- [ ] Every gateway that includes Matter tools uses **Arcade Auth** mode.
- [ ] The project's members are only the token owner. Arcade Auth admits every project
      member, and every member would act on the owner's library.
- [ ] No API keys exist in the project that you don't use. Anyone holding one can call the
      project's tools.

## 2. Tool exposure

- [ ] List every gateway in the project and the Matter tools each exposes. Check each
      matches its purpose (a read-only gateway has only the tools tagged read-only).
- [ ] Check for other ways to invoke the tools in the project (other gateways, API keys,
      agents or integrations using the project) and remove any you don't use.
- [ ] Note which clients are connected to each gateway, and remove any you don't recognize.

## 3. Worker protection

Arcade Cloud gives the deployed worker a generated `ARCADE_WORKER_SECRET`; Arcade calls the
worker's `/worker/*` routes with tokens signed by it. `/worker/health` is unauthenticated
by design. `ARCADE_AUTH_DISABLED=true` turns the worker's check off; `arcade deploy` sets
it only on the throwaway local copy it starts to validate the server before upload.

- [ ] In the deployment's settings, confirm no `ARCADE_AUTH_DISABLED` variable is set (or
      it's `false`), and that `ARCADE_WORKER_SECRET` isn't overridden with a value of your
      own.
- [ ] Find the worker's URL in the dashboard, then run, with no credentials:

      ```bash
      uv run scripts/check_unauthenticated_access.py https://<worker-url>
      ```

      It first requires `/worker/health` to answer 200, so a typo or a gateway URL fails
      instead of passing. It then asks for `/worker/tools`, `/worker/tools/invoke` and the
      MCP route without credentials. It passes only if each is refused, and treats an MCP
      route that accepts an anonymous `initialize` as exposed unless `tools/list` is
      refused too. It never sends a token or calls a tool. Exit 0 means only that these
      probes were refused, not that only you can call the tools. If the MCP check fails,
      record it and ask Arcade whether the worker's `/mcp` route should be reachable.

For reference, a local `uv run src/arcade_matter/server.py http` with
`ARCADE_WORKER_SECRET` set refuses `/worker/tools` and `/worker/tools/invoke` (401), but
serves the MCP tool list to anyone. Its MCP route refuses to run tools that need secrets
over HTTP, so no Matter call happens. That's why the script checks the MCP route too.

## 4. Deployed revision and dependencies

- [ ] Record the Git commit that was deployed (deploy from a clean checkout of `main`, and
      note `git rev-parse HEAD` at the time).
- [ ] Record the installed versions of at least `arcade-mcp-server`, `arcade-core`,
      `arcade-serve`, `httpx`, `mcp`, `starlette`, `uvicorn` and `pydantic` from the
      deployment's build output or logs. Lockfile versions don't prove what was installed:
      `arcade deploy` resolves `pyproject.toml`'s ranges at build time.
- [ ] Compare them with the lockfile for that commit:

      ```bash
      uv export --locked --no-dev --no-hashes --no-emit-project > /tmp/locked.txt
      ```

- [ ] Check the deployed versions for advisories, for example with
      `uvx pip-audit -r <file of deployed name==version lines> --no-deps --disable-pip`, and
      the GitHub advisory database for anything flagged. Redeploy if a fixed version exists.

## Record

| Date | Checked by | Gateways and auth mode | Project members | Worker URL check | Deployed commit | Versions match lockfile | Advisories |
|---|---|---|---|---|---|---|---|
| | | | | | | | |
