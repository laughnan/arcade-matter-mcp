# Read and write gateways

Matter's API token has no scopes, so every tool on this server can do anything the token
owner can, including permanent deletes. The server can't tell a user's request from a
manipulated model's, and asking the model to confirm first (as the server instructions do)
is advice, not enforcement: when a client calls `Matter.DeleteItem`, the item is deleted.

So the controls live outside the server:

1. **A read-only gateway for routine use.** It exposes no tool that can change the library,
   so nothing that happens on that connection can modify or delete anything.
2. **A separate write gateway, used only when you mean to change something,** connected
   through a client that asks you to approve every write call, showing the exact tool and
   arguments, before it runs.

Don't treat an extra model-supplied argument (such as `confirm: true`) as a safeguard. The
model that would be manipulated is the one filling it in.

## Which tools go where

Every tool declares `ToolMetadata` behavior flags. `tests/test_gateway_tools.py` keeps the
lists below in step with them.

Read-only gateway (`read_only` is true):

<!-- read-tools:start -->
- `Matter.GetAccount`
- `Matter.GetItem`
- `Matter.GetItemContent`
- `Matter.GetItemWithHighlights`
- `Matter.ListHighlights`
- `Matter.ListItems`
- `Matter.ListReadingSessions`
- `Matter.ListRecentHighlights`
- `Matter.ListTags`
- `Matter.SearchLibrary`
- `Matter.SummarizeReadingTime`
<!-- read-tools:end -->

Write gateway: the read tools (so the model can look up IDs) plus these.

<!-- write-tools:start -->
- `Matter.AddTag`
- `Matter.RemoveTag`
- `Matter.RenameTag`
- `Matter.SaveItem`
- `Matter.SetHighlightNote`
- `Matter.UpdateItem`
<!-- write-tools:end -->

Destructive (`destructive` is true). Include these only if you need them, and never
auto-approve them:

<!-- destructive-tools:start -->
- `Matter.DeleteHighlight`
- `Matter.DeleteItem`
- `Matter.DeleteTag`
<!-- destructive-tools:end -->

## Setting it up

1. In the Arcade dashboard, create a gateway named, say, `matter-read`. Select only the
   read-only tools above and choose **Arcade Auth**.
2. Create a second gateway, `matter-write`, with the read tools plus the write tools you
   want (and the destructive ones only if you need them). Also **Arcade Auth**.
3. Keep the project to yourself. Both gateways act on your library with your token, and
   Arcade Auth admits every project member.
4. Connect your everyday clients to `matter-read` only.
5. Connect `matter-write` only in a client that can require approval per tool, and set it
   to ask for every write tool:
   - **Claude Code:** list the write tools under `permissions.ask` in
     `.claude/settings.json`, with the names the gateway gives them (run `/mcp` to see
     them), for example `"ask": ["mcp__matter-write__Matter_DeleteItem", ...]`. Don't put
     any write tool, or a wildcard covering the server, in `allow`, and don't run that
     client in a mode that skips permission prompts.
   - **Claude Desktop and claude.ai:** set each write tool to **Needs approval**, never
     **Always allow**.
   - A client that can't require approval per tool shouldn't get the write gateway.

## Verifying it

Use a throwaway item you saved for the test, not real library data.

1. **The read connection can't write.** In a client connected only to `matter-read`, list
   its tools and check none of the write or destructive tools appear. Then ask it to
   archive or delete the test item. It should have no tool to do it, and the item should
   be unchanged in Matter.
2. **Writes wait for approval.** In the client connected to `matter-write`, ask it to
   delete the test item. The client should stop and show `Matter.DeleteItem` with that
   item's ID before anything runs. Deny it, and check the item still exists. Approve a
   second attempt and check it's gone.
3. **Approval shows the exact target.** Ask it to save a URL with a query string, and check
   the approval prompt shows the whole URL, query included, before you approve.

Record the date, the gateway slugs and the tool lists you checked. Don't record your token
or library contents.
