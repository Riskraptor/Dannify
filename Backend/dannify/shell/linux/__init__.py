"""The Linux shell: a GTK window with WebKit inside (pywebview's GTK backend).

Split by what each part talks to: ``gtk`` (the toolkit and its thread),
``tray`` (the AppIndicator icon), ``mpris`` (media keys and the desktop's
media panel, over D-Bus), ``desktop`` (autostart, file manager, dock progress,
shortcuts, theme), ``login`` (the Google sign-in window), ``updater`` (the
signed .deb), ``api`` (the bridge calls) and ``app`` (start-up and shut-down).
"""
