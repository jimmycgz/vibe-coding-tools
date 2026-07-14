# Example permissions (Claude Code) — adopt at your own risk

These are **example** `permissions` entries that let this skill run without approval prompts. They
reflect the author's risk tolerance on a personal dev machine — **they are not a security boundary,
and you own the decision to use them.** Read the "what this does / doesn't guarantee" section before
copying anything.

> ⚠️ **Merge, don't replace.** These are a *fragment* of `~/.claude/settings.json`. Add the entries
> to your existing `permissions.allow` / `permissions.deny` arrays — do not overwrite the whole file
> (you'd wipe your other settings). Nothing here is machine- or account-specific; there is
> deliberately **no `env`, model, hook, or path** in this example — those are yours to keep.

## The allowlist (read-only — allowlist at your own risk)

```json
{
  "permissions": {
    "allow": [
      "WebFetch",
      "Bash(gh search:*)",
      "Bash(gh issue view:*)",
      "Bash(gh pr view:*)",
      "Bash(gh repo view:*)",
      "Bash(gh-get:*)",
      "Bash(jq:*)",
      "Bash(grep:*)",
      "Bash(head:*)",
      "Bash(tail:*)",
      "Bash(sort:*)"
    ]
  }
}
```

Every entry above is read-only *by its nature* — the subcommand IS the read operation, so no flag
can flip it into a write. `gh-get` is the bundled GET-only wrapper ([`../scripts/gh-get`](../scripts/gh-get));
put it on your `PATH` first. `curl` and bare `gh api` are **intentionally absent** — they are
general-purpose and a prefix rule can't restrict them to GET, so let them prompt (or use `gh-get` /
WebFetch instead).

## The denylist (defense-in-depth for auto/bypass mode)

```json
{
  "permissions": {
    "deny": [
      "Bash(gh repo delete:*)",
      "Bash(gh secret:*)",
      "Bash(gh auth:*)",
      "Bash(gh api -X:*)",
      "Bash(gh api --method:*)"
    ]
  }
}
```

`deny` takes precedence over `allow`, so these hold even if you later broaden the allowlist. In
interactive mode they are belt-and-suspenders (unlisted commands already prompt); in auto/bypass
mode they are a real floor, because auto-mode won't prompt on its own.

## What this does and does NOT guarantee (defense-in-depth)

- **What it does:** removes friction for read-only work and hard-blocks a few high-blast mutations.
- **What it does NOT:** it is **not** airtight. Bash rules are prefix-matched and flag-agnostic, so a
  deny cannot catch a mutation flag that trails the path (`gh api repos/o/r -X DELETE` shares the
  allowed prefix if you ever allow `gh api`). Treat these rules as the *convenience* layer.
- **Stronger layers, in order of how practical they are for a normal user:**
  1. **The `gh-get` wrapper (practical default, zero setup)** — because it forces `--method GET` in
     code, it can't mutate *no matter what token you're using*. This is the realistic boundary for
     most people: you keep your normal full-scope `gh auth`, and raw-API reads still can't write. Use
     it instead of raw `gh api`.
  2. **Sandbox / VM (for high-autonomy runs)** — run agents where the blast radius is a disposable
     box. The right choice when you're letting an agent go unattended.
  3. **Least-privilege credential (optional hardening)** — a read-scoped `gh` token makes mutations
     fail at the API. It's the most airtight, but most users won't set one up and that's fine — it's
     an advanced option, not a prerequisite. Don't rely on this being in place.
  4. **Server-side / org policy** — controls no local command can bypass (not usually user-set).

Realistic posture for the normal case: **allow the read-only verbs + use `gh-get` for raw reads**,
and reach for the sandbox when running unattended. The scoped token is a nice-to-have on top, not a
requirement. Never rely on the allow/deny list *alone* on a machine or credential you can't afford
to have mutated.
