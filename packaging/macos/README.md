# Dannify for macOS

Dannify runs on macOS 11 (Big Sur) and later, on Apple silicon and Intel Macs.
Each release has one download per processor:

| File | For |
| --- | --- |
| `macos-Dannify-<version>-arm64.dmg` | Apple silicon (M1 and later) |
| `macos-Dannify-<version>-x64.dmg` | Intel Macs |

The matching `.zip` files are what the app updates itself from; you do not
need them.

## Installing

1. Open the `.dmg`.
2. Drag **Dannify** onto **Applications**.
3. Eject the disk image, then open Dannify from Applications (or Launchpad).

Run it from Applications, not straight from the disk image or the Downloads
folder: macOS runs apps opened from there from a hidden read-only copy, and
Dannify cannot update itself from one.

## The first time you open it

Dannify is not from the App Store and is not notarised by Apple (that needs
a paid Apple Developer account). It is signed, but only "ad hoc", so the first
time you open it macOS says it cannot check it for malicious software. You
tell macOS once that you trust it, and after that it opens like any other app.

**macOS 15 (Sequoia) and later**

1. Open Dannify. macOS says it "cannot be opened" or "is not opened"; click
   **Done** (not "Move to Bin").
2. Open **System Settings > Privacy & Security** and scroll down to the
   **Security** section. Next to "Dannify was blocked to protect your Mac",
   click **Open Anyway**, and confirm with your password or Touch ID.
3. Open Dannify again and click **Open Anyway** once more.

**macOS 14 (Sonoma) and earlier**

1. In Applications, right-click (or Control-click) **Dannify** and choose
   **Open**.
2. Click **Open** in the warning. (Opening it by double-click the first time
   only offers "Move to Trash" and "Cancel"; the right-click way is the one
   with an Open button.)

If macOS says Dannify "is damaged and can't be opened", download it again
from the release page first (a cut-off download looks like this). If the new
copy says the same, its download flag is what macOS objects to; with Dannify
in Applications, this in Terminal clears it:

```sh
xattr -dr com.apple.quarantine /Applications/Dannify.app
```

## What it does on a Mac

- Its window has the usual red, yellow and green buttons, full screen, and a
  compact player that floats above other windows.
- Closing the window keeps the music playing. Dannify stays in the Dock and in
  the menu bar (the note icon); either brings the window back. **Quit** from
  the Dannify menu, the Dock or the menu bar icon ends it.
- The keyboard's play, next and previous keys, AirPods and Control Center's Now
  Playing control it. The global shortcuts (Control-Option-P, Control-Option-Left,
  Control-Option-Right) can be switched on in Settings.
- **Open at login** (Settings) adds a login item that starts it hidden.
- Double-clicking a saved `.dnf` song opens it in Dannify.
- Its settings and library data live in `~/Library/Application Support/Dannify`;
  songs go to `~/Music/Dannify` unless you pick another folder.

## Updates

Dannify checks for new versions itself. When one is ready it is downloaded,
checked against the release's signature (a key only the author holds), and
put in place either straight away ("Restart to update") or when you next quit.

What happens then: the new Dannify.app is unpacked next to the one you have,
its code signature is checked, and once Dannify has quit the old app is set
aside as `Dannify.app.old` and the new one takes its place. If the new version
does not start properly within about 40 seconds, the old one is put back and
started instead, and that version is not offered again. Once the new version
is running it deletes `Dannify.app.old`.

Updating in place needs Dannify to be somewhere you can write to, which
Applications is for an administrator account. If it is not (a standard
account with Dannify in the shared Applications folder, or the app opened
straight from Downloads), Dannify points you to the download page instead.

## Removing it

Quit Dannify, then drag it from Applications to the Bin. To remove its data
as well, delete `~/Library/Application Support/Dannify` and, if you turned on
Open at login, `~/Library/LaunchAgents/io.github.danielmwendwa9451.dannify.plist`.
Your music folder is left alone.

## Building it

`.github/workflows/release.yml` builds both versions on GitHub's Mac runners;
to build on a Mac yourself, with Xcode's command line tools:

```sh
cd frontend && npm ci && npx vite build && cd ..
python3 -m pip install -r Backend/requirements.txt pyinstaller
bash packaging/macos/build-media.sh        # FFmpeg, LGPL only (brew install nasm first on Intel)
bash packaging/macos/build.sh              # Dannify.app, the .zip and the .dmg, in packaging/macos/out
python3 packaging/macos/smoke_test.py packaging/macos/out/macos-Dannify-*-arm64.zip
```

The release machine signs the `.zip` and `.dmg` with the release key
(`packaging/release_key.py`) before they are published; the app only installs
an update whose signature checks out.
