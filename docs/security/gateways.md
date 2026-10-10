# Read and write gateways

Matter's API token has no scopes, so every tool on this server can do anything the token
owner can, including permanent deletes. The server can't tell a user's request from a
manipulated model's, and asking the model to confirm first (as the server instructions do)
is advice, not enforcement: when a client calls `Matter.DeleteItem`, the item is deleted.

So the controls live outside the server:

1. **A read-only gateway for routine use.** It exposes no tool that can change the library,
   so nothing that happens on that connection can modify or delete anything.
2. **A separate, write-only gateway, used only when you mean to change something,**
   connected through a client that asks you to approve every call to it, showing the
   exact tool and arguments, before it runs. A client that needs it also connects the
   read-only gateway and looks up IDs there.

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

Write gateway: only these. It doesn't include the read tools; a client that writes also
connects the read-only gateway to look up IDs, so no read tool is offered on a connection
that can also change the library.

<!-- write-tools:start -->
- `Matter.AddTag`
- `Matter.RemoveTag`
- `Matter.RenameTag`
- `Matter.SaveItem`
- `Matter.SetHighlightNote`
- `Matter.UpdateItem`
<!-- write-tools:end -->

Destructive (`destructive` is true). Add these to the write gateway only if you need
them, and never auto-approve them:

<!-- destructive-tools:start -->
- `Matter.DeleteHighlight`
- `Matter.DeleteItem`
- `Matter.DeleteTag`
<!-- destructive-tools:end -->

## Setting it up

1. In the Arcade dashboard, create a gateway named, say, `matter-read`. Select only the
   read-only tools above and choose **Arcade Auth**.
2. Create a second gateway, `matter-write`, with only the write tools above, plus the
   destructive ones if you need them. No read tools. Also **Arcade Auth**.
3. Keep the project to yourself. Both gateways act on your library with your token, and
   Arcade Auth admits every project member.
4. Connect your everyday clients to `matter-read` only.
5. Connect `matter-write` (alongside `matter-read`) only in a client that can require
   approval for every call to it:
   - **Claude Code:** add the whole write server to `permissions.ask` in
     `.claude/settings.json`, using the name you gave the connection (run `/mcp` to see
     it), for example `{"permissions": {"ask": ["mcp__matter-write"]}}`. A server-level
     rule covers every tool on it, including write tools added later, and because the
     gateway has no read tools it never prompts for reads. Never put `mcp__matter-write`
     or any of its tools in `allow`. When prompted, approve once; "Yes, and don't ask
     again" saves an `allow` rule and removes the control. Don't use this client in
     `bypassPermissions` mode, and don't rely on `auto` mode, which lets a classifier
     approve calls in your place.
   - **Claude Desktop and claude.ai:** set every tool on the write connection to **Needs
     approval**, never **Always allow**.
   - A client that can't require approval for every call to a connection shouldn't get
     the write gateway.

## Verifying it

Use a throwaway item you saved for the test, not real library data. Approve each prompt
once; never choose an option that stops future prompts.

1. **The read connection can't write.** In a client connected only to `matter-read`, list
   its tools and check none of the write or destructive tools appear. Then ask it to
   archive the test item. It should have no tool to do it, and the item should be
   unchanged in Matter.
2. **Writes wait for approval.** In the client connected to `matter-write`, ask it to
   favorite the test item. The client should stop and show `Matter.UpdateItem` with that
   item's ID and `favorite: true` before anything runs. Deny it, and check the item isn't
   favorited. Ask again, approve once, and check it is.
3. **Approval shows the exact target.** Ask it to save a URL with a query string, and check
   the approval prompt shows the whole URL, query included, before you approve.
4. **Deletes, if you added them.** Ask it to delete the test item. Check the prompt shows
   `Matter.DeleteItem` with that item's ID, deny it, and check the item still exists.

Record the date, the gateway slugs and the tool lists you checked. Don't record your token
or library contents.
