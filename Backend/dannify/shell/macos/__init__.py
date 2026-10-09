"""The macOS shell: a Cocoa window with WebKit inside (pywebview's Cocoa backend).

Split by what each part talks to: ``cocoa`` (AppKit and its main thread),
``tray`` (the menu bar item), ``nowplaying`` (media keys and Control
Center's Now Playing), ``desktop`` (login items, Finder, the Dock, sound
settings, shortcuts, theme), ``login`` (the Google sign-in window),
``updater`` (swapping in a new Dannify.app), ``api`` (the bridge calls) and
``app`` (start-up and shut-down).
"""
