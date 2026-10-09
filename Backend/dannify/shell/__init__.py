"""The desktop shells: the native window around the interface.

``core`` and ``instance`` are what every platform shares. Each platform has
its own package beside them (``windows``, ``linux``, ``macos``) answering the
same bridge calls (frontend/src/desktop/bridge.js), so the interface never
needs to know which one it is in beyond the platform name win_state reports.
"""
