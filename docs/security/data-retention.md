# Execution logs and training consent

The read tools return personal data: the account email, library titles and URLs, full
article text, highlights and notes. Arcade can record tool inputs and results in execution
logs, and has a training-consent control for them. Keeping a gateway private controls who
can call the tools; it doesn't stop the platform from keeping what they returned.

This server doesn't log tool inputs or results itself. It logs at `INFO` (request lines and
startup), and its errors carry Matter's error text and request paths, which contain item,
highlight and tag IDs but not content.

## Settings to review

Check these in the Arcade dashboard for the organization and for the project the server is
deployed in. Use Arcade Cloud's documentation for where each setting lives:
<https://docs.arcade.dev/en/operate/deploy/arcade-cloud>.

- [ ] **Execution-log collection.** Turn off recording of tool inputs and results if you
      don't need it for debugging. If you keep it, prefer recording metadata (tool name,
      time, status) over full inputs and results.
- [ ] **Retention period.** If logs are kept, choose the shortest period that still covers
      debugging (days, not months).
- [ ] **Training consent.** Opt out, at both organization and project level if both exist,
      unless you want your library's content used for training.
- [ ] **Who can read logs.** List the people and API keys that can view execution logs or
      recorded results, and remove anyone who doesn't need to. This should match the
      owner-only project membership.
- [ ] **Client side.** MCP clients keep their own transcripts of tool results (for example
      chat history). Review their retention and training settings as well.

## Verifying the change

After changing the settings, call a read tool whose result is harmless, such as
`Matter.ListTags` or `Matter.GetAccount`, then check the execution log for that call:

- with collection off, no inputs or results are recorded;
- with collection on, the retention period and visibility match what you chose.

Don't use a call that returns article text or notes for this check, and don't copy log
contents, article text, notes or credentials into the record below or into issues or tasks.

## Record

| Date | Checked by | Log collection | Retention | Training consent | Who can view logs | Verified with |
|---|---|---|---|---|---|---|
| | | | | | | |
