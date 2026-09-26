# Ship-time configuration

Anything in this folder is copied into the app folder
(`<install dir>\app\config\`) by `packaging\build.ps1`, so it ships with every
release and every update, and is read at startup. Nothing here is secret:
only public keys and URLs. So it is safe to commit and to ship.

Precedence, lowest to highest:

1. `<install dir>\app\config\<file>.json`: what you ship (this folder)
2. `%LOCALAPPDATA%\Dannify\<file>.json`: a per-machine override
3. environment variables: handy for testing

## updates.json: where the updater looks for releases

```json
{ "repo": "your-user/your-repo", "channel": "stable" }
```

* `repo`: the GitHub repository whose **Releases** the app checks. Tag each
  release `v4.0.1` (the leading `v` is optional) and attach what
  `packaging\build.ps1` produces: `Dannify-Setup-<v>.exe`, `package-<v>.json`
  and `package-<v>.zip`. `packaging\publish.ps1` does exactly that.
* `channel`: `stable` (default) uses GitHub's "latest release"; `prerelease`
  also picks up releases marked as pre-release.

Environment override: `DANNIFY_UPDATE_REPO=your-user/your-repo`.

The whole flow is already wired: Dannify checks 8 seconds after launch and
every 6 hours, gets a new version ready in the background (only the files
that changed are downloaded), then shows "Restart to update". Ignore it and
the new version is simply there the next time Dannify opens. Your library,
settings and sign-in all carry over.

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
