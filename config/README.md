# Live settings

`support-live.json` is how Dannify's payment details change between releases:
the PayPal link, the M-Pesa till or paybill, and the line on the Support page.
Every installed copy reads it from this branch twice a day, and believes it
only when `support-live.json.dsig` is the release key's signature over it.

To change them:

1. Edit `support-live.json` and raise `"version"` by one. A copy never goes
   back to a lower version than the one it has.
2. Sign it with the release key (the same one releases are signed with):

   ```
   python packaging/release_key.py sign-support
   ```

3. Commit both files to `main`. Copies pick them up within twelve hours, or at
   their next start.

Only `paypal`, `mpesa` and `message` are read from here, and each is checked as
strictly as the built-in ones (a PayPal link must be a PayPal payment link or
paypal.me name; an M-Pesa number must be a till or paybill).
