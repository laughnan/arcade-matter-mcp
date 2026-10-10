# Execution logs and training consent

These tools return personal data: the account email and name, library titles and URLs,
full article text, highlights, notes and tag names. That covers read tools, composite
tools (`ListRecentHighlights`, `GetItemWithHighlights`) and writes too: `SaveItem` returns
the saved title and URL, and `SetHighlightNote` returns the note and highlight text.
Arcade can store tool inputs and results in execution records, and can use them for
training unless you opt out. Keeping a gateway private controls who can call the tools; it
doesn't stop the platform from keeping what they returned.

This server doesn't log tool inputs or results itself. At `INFO` it logs request lines,
tool names and timing. Arcade Cloud keeps those application logs under its own retention,
separately from execution records. Its user-facing errors include Matter's error message
and the IDs in the request.

Arcade's [Tool executions](https://docs.arcade.dev/en/operate/governance/tool-executions)
and [Arcade Cloud](https://docs.arcade.dev/en/operate/deploy/arcade-cloud) pages are the
sources for the settings below. Confirm each against the dashboard when you review it,
since these settings change.

## Execution recording and retention

- [ ] Open **Organization → Logging Policy**. Recording and retention are organization-wide
      and apply to every project in the org; there is no per-project switch.
- [ ] Recording is **on by default**, and when it's on Arcade stores full inputs and
      outputs. There is no metadata-only mode. To store no new Matter content, turn
      recording **off**.
- [ ] If you keep recording on, set the shortest retention window that covers debugging.
      It defaults to 7 days and can be 1 to 90 days on Arcade Cloud.
- [ ] Know what the changes don't do. Turning recording off stops new records but doesn't
      erase existing ones. Shortening the window deletes older records across **every**
      project in the org, and that can't be undone.

## Training consent

- [ ] As an organization admin, opt out of training consent. Consent is scoped to the
      organization.
- [ ] Opting out stops future collection and excludes existing data from later training
      runs, but doesn't delete data already collected. Training data (tool queries,
      inputs, and results from external services, meaning Matter library content) can be
      kept for up to 5 years. A checked box here doesn't mean earlier library content is
      gone. If you need that, ask Arcade about deletion.

## Who can see execution data

- [ ] Project and organization **admins** can open recorded inputs and outputs. Keep the
      org's admins to people you'd trust with your library.
- [ ] Every **project member** can see the execution list, timing and each attempt's
      model-facing error. For this server that includes Matter's error message and item,
      highlight or tag IDs. Arcade withholds `developer_message` along with the payload.
      Owner-only project membership (see the gateway setup) keeps this to you.
- [ ] A regular project **API key** can list execution history without payloads. Remove
      keys you don't use.
- [ ] **Client side:** MCP clients keep their own transcripts of tool results (for example
      chat history). Review their retention and training settings as well.

## Verifying the change

- **Recording off:** call any tool. Then check that the call either doesn't appear in the
  execution records or appears with no stored inputs and outputs. Don't open stored
  outputs to check, and don't use a tool that returns the account email
  (`Matter.GetAccount`).
- **Recording on:** the result of the call you use to check will be stored for the whole
  retention window, so pick one whose output you accept storing. `Matter.ListTags` returns
  tag names, which are library metadata.

Don't copy log contents, article text, notes, the account email or credentials into the
record below or into issues or tasks.

## Record

| Date | Checked by | Recording | Retention window | Training consent | Org and project admins | Verified with |
|---|---|---|---|---|---|---|
| | | | | | | |
