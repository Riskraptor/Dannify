# Live settings

`support-live.json` is how Dannify's ways to give change between releases:
the GitHub Sponsors account, the PayPal link, the Ko-fi page, and the line on
the Support page. Its `"mpesa": {}` is for copies from 4.14.0 and 4.14.1, which
offered M-Pesa: it keeps it hidden there. M-Pesa is gone from Dannify.

Every installed copy reads it from this branch when it starts and twice a day
after, keeps it for when it is offline, and believes it only when
`support-live.json.dsig` is the release key's signature over it. A copy never
goes back to a lower version than the one it has.

## See what copies are told

```
python packaging/support_details.py
```

## Change it

One command: it raises the version, signs with the release key (the same one
releases are signed with, from `DANNIFY_RELEASE_KEY` or
`~/.dannify/release-signing.key`), and checks the result exactly as the app
does.

```
python packaging/support_details.py --github Riskraptor
python packaging/support_details.py --paypal https://www.paypal.com/ncp/payment/PLB-XXXXXXXXXXXX
python packaging/support_details.py --kofi https://ko-fi.com/yourname
python packaging/support_details.py --message "Thank you for keeping Dannify free!"
python packaging/support_details.py --no-paypal       (stop showing PayPal)
```

Then commit `support-live.json` and `support-live.json.dsig` to `main` (through
a pull request). Copies pick them up within twelve hours, or at their next
start.

Each value is checked as strictly as the built-in ones: a PayPal link must be a
PayPal payment link or a paypal.me name, the GitHub account a GitHub name, the
Ko-fi page an https address. Nothing else in the file is read: which
repository updates come from, and everything else about the app, stay as
built.

# Live fixes

`live.json` is how a fix reaches every installed copy without a new version
(see `Backend/dannify/live.py`). It is read and believed the same way as
`support-live.json`: signed with the release key, never rolled back, checked
at start and every three hours, kept for when there is no connection.

It can carry three things:

- `clients`: the identities YouTube is asked with. When songs stop playing
  everywhere at once because YouTube changed what it accepts, this puts it
  right everywhere at once, with no update to install.
- `emergency`: a fix build that copies in a range should take now. The build
  is published like any release, tagged with a fourth number (`v4.15.0.1`,
  shown as "4.15.0 · fix 1"); copies between `from` and it say plainly that an
  important fix is ready and fetch it straight away, even while music plays.
- `notice`: one line everyone sees once (a service being down).

```
python packaging/live_details.py                                   (what copies are told)
python packaging/live_details.py --clients Backend/dannify/clients.json
python packaging/live_details.py --emergency 4.15.0.1 --from 4.15.0 --note "Songs play again"
python packaging/live_details.py --notice outage-1 --notice-text "YouTube is down; saved music plays" --days 2
python packaging/live_details.py --no-emergency --no-notice
```

Then commit `live.json` and `live.json.dsig` to `main` (through a pull request).
