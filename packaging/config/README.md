# Ship-time configuration

Anything in this folder is copied to `<install dir>\config\` by the installer
and read at startup. Nothing here is secret: only public keys and URLs. So
it is safe to commit and to ship.

Precedence, lowest to highest:

1. `<install dir>\config\<file>.json`: what you ship (this folder)
2. `%LOCALAPPDATA%\Dannify\<file>.json`: a per-machine override
3. environment variables: handy for testing

## updates.json: where the updater looks for releases

```json
{ "repo": "your-user/your-repo", "channel": "stable" }
```

* `repo`: the GitHub repository whose **Releases** the app checks. Tag each
  release `v3.0.1` (the leading `v` is optional) and attach the installer
  the updater picks the first asset ending in `.exe`, preferring one with
  `setup` in the name, which is exactly what `packaging\build.ps1` produces.
* `channel`: `stable` (default) uses GitHub's "latest release"; `prerelease`
  also picks up releases marked as pre-release.

Environment override: `DANNIFY_UPDATE_REPO=your-user/your-repo`.

The whole flow is already wired: Dannify checks 8 seconds after launch and
every 6 hours, shows a download arrow in the title bar, streams the installer
with a progress ring, then closes itself and runs it. Your library, settings
and sign-in all survive the upgrade.

## support.json: donations (Paystack)

Two ways to take a tip; pick whichever you prefer.

**A. Payment Page (simplest, no keys in the app):**

```json
{ "payment_link": "https://paystack.shop/pay/your-page" }
```

**B. Paystack Inline with your PUBLIC key:**

```json
{
  "public_key": "pk_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "currency": "KES",
  "amounts": [200, 500, 1000, 2000],
  "email": "you@example.com",
  "message": "Dannify is free. A tip keeps it growing."
}
```

Only the **public** key is ever used, and checkout opens in the user's real
browser: card details never touch Dannify. `amounts` become the quick-tip
buttons in Settings → Support; the section stays hidden until one of
`payment_link` or `public_key` is set.

Environment overrides: `DANNIFY_PAYSTACK_PUBLIC_KEY`, `DANNIFY_DONATE_LINK`,
`DANNIFY_DONATE_CURRENCY`, `DANNIFY_DONATE_AMOUNTS` (comma separated),
`DANNIFY_DONATE_EMAIL`, `DANNIFY_DONATE_MESSAGE`, `DANNIFY_DONATE_DISABLED=1`.
