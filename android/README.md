# Dannify for Android

Dannify runs on Android 7.0 and later, on phones and tablets with a 64-bit
processor (nearly every one sold since 2017). It is the same app as on a
computer: the same interface, the same library, the same lyrics, Spotify
links and special days, running on the phone itself. Nothing is streamed
from a computer, and nothing needs one.

Each release has one download per processor:

| File | For |
| --- | --- |
| `android-Dannify-<version>-arm64.apk` | Phones and tablets (almost all of them) |
| `android-Dannify-<version>-x86_64.apk` | Chromebooks and the emulator on a PC |

## Installing

1. On the phone, open the release page and download the `arm64` APK.
2. Open it from the download notification or the Files app. Android asks
   whether the browser (or Files) may install apps: allow it, go back, and
   tap **Install**.
3. Open Dannify. The first start takes a few seconds longer than the rest:
   the app unpacks itself once.

Dannify is not from the Play Store, so Play Protect may say it does not know
the app. That is all it means: tap **More details**, then **Install anyway**.

## Updates

Dannify updates itself, as on a computer. A new version is found, fetched
and checked against Dannify's release key before anything is done with it,
and then Dannify says once that it is ready. Android asks you to confirm the
update; Dannify closes while it installs, and Android's installer offers to
open it again. Your library, settings and sign-in are kept.

Updates only ever install over a Dannify signed with the same key: Android
refuses anything else, whatever it is called.

## What it does on a phone

- The music plays on with the screen off, from the lock screen, and with
  Dannify swiped away from the recent apps. Pause it and swipe it away, and
  it goes.
- The notification and the lock screen show the song, its cover and its
  buttons; so do headphones, cars and watches.
- A call pauses the music and it comes back afterwards. Unplugging the
  headphones pauses it. Another app starting its own music pauses it for
  good.
- Share a song, album or playlist from Spotify, YouTube or YouTube Music to
  Dannify, or open a link with it, and it opens there.
- Back closes whatever is open, then goes back a page; at the start it steps
  aside and leaves the music playing.
- Signing in opens Google's own page, in a screen of its own. Dannify never
  sees your password, and signing out wipes everything that page kept.
- Saved songs are kept in Dannify's own folder on the phone, sealed as on a
  computer, and go with the app if it is uninstalled.

## Building it

What a build needs, on Windows, Linux or macOS:

- JDK 17 or later (`JAVA_HOME`), and the Android SDK with platform 36
  (`ANDROID_HOME`, or `sdk.dir` in `android/local.properties`).
- Python 3.14, the version the app carries: Chaquopy compiles the app's
  Python with it. `DANNIFY_BUILD_PYTHON` names it if `python` is another one.
- Node, to build the interface.
- What is built for Android that nobody publishes: pydantic-core, the media
  tool (FFmpeg) and QuickJS. The **Android native** workflow
  (`.github/workflows/android-native.yml`) builds them; its artifact goes in
  `android/native/`:

  ```sh
  gh run download <run> --repo Riskraptor/Dannify --name android-native --dir android/native
  ```

Then:

```sh
cd frontend && npm ci && npx vite build && cd ..
cd android
./gradlew assembleArm64Debug      # a phone
./gradlew assembleX86_64Debug     # the emulator
```

Every build runs `tools/prepare.py` first, which packs the interface into
the app and puts the programs where Android installs them. A debug build is
called Dannify too, but installs beside the real app (`app.dannify.dev`)
instead of over it, and its page can be inspected from Chrome
(`chrome://inspect`).

`./gradlew assembleArm64Release assembleX86_64Release` makes the release
APKs, unsigned: the release workflow does that on every tag, and
`packaging/publish.ps1` signs them on the release machine, first with the
app's own key and then with the release key, like every other platform's
files.

## The app's signing key

Android installs an update only over an app signed with the same key, so
the key every Dannify APK is signed with can never change. It is kept on the
release machine only, with its password in a file beside it, and backed up
offline:

- `DANNIFY_APK_KEYSTORE` names it (default `~/.dannify/dannify.keystore`);
- `DANNIFY_APK_KEYSTORE_PASSWORD`, or the file `<keystore>.password`, holds
  its password;
- `packaging/android/certificate.sha256` is its certificate's fingerprint,
  which `publish.ps1` checks every APK against before anything is signed
  with the release key.

## How it fits together

| Part | What it is |
| --- | --- |
| `Backend/` | The backend, run in the app by Chaquopy, started by `dannify/shell/android/host.py` |
| `app/src/main/java/app/dannify/` | The app around it: the page, the media session, sign-in, updates |
| `frontend/src/desktop/bridge.js` | Where the interface asks the app for things, under the same names as on a desktop |
| `tools/prepare.py` | Packs the interface and places the programs, before every build |
| `packaging/android/` | How the media tool and QuickJS are built for Android |
