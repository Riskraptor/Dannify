# Third-party notices

Dannify is licensed under the MIT License (see [LICENSE](LICENSE)). It is
built with, and ships, the components below. Each remains under its own licence, and nothing
in Dannify's licence limits the rights those licences give you.

## Code Dannify grew from

Dannify's user interface began as the web interface of spotDL, used under the
MIT License:

```
MIT License

Copyright (c) 2023 spotDL

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Components in the installed app

| Component | Licence |
| --- | --- |
| Python runtime | Python Software Foundation License 2.0 |
| PyInstaller bootloader | GPL-2.0-or-later with the bootloader exception, which allows it in programs under any licence |
| pywebview | BSD-3-Clause |
| FastAPI | MIT |
| Starlette | BSD-3-Clause |
| Uvicorn | BSD-3-Clause |
| Pydantic | MIT |
| AnyIO | MIT |
| websockets | BSD-3-Clause |
| yt-dlp | Unlicense (public domain) |
| yt-dlp challenge solver scripts (yt-dlp-ejs) | Unlicense, with the parts it bundles under MIT and ISC |
| QuickJS-ng (`dnfjs.exe`), the JavaScript engine those scripts run in | MIT |
| ytmusicapi | MIT |
| requests | Apache-2.0 |
| urllib3 | MIT |
| idna | BSD-3-Clause |
| charset-normalizer | MIT |
| certifi | MPL-2.0 |
| Loguru | MIT |
| tinytag | MIT |
| Python.NET (pythonnet), clr-loader | MIT |
| Microsoft Edge WebView2 SDK libraries (`Microsoft.Web.WebView2.Core.dll`, `Microsoft.Web.WebView2.WinForms.dll`, `WebView2Loader.dll`) | Microsoft WebView2 SDK licence, which allows them to ship with apps |
| Vue, Vue Router | MIT |
| axios, uuid | MIT |
| Iconify, Phosphor icons | MIT |
| Inter, Plus Jakarta Sans (fonts) | SIL Open Font License 1.1 |

### FFmpeg and LAME

Dannify's media tool (`dnfmedia.exe`) is FFmpeg 7.1.2 with the LAME MP3
encoder, built as a separate program that Dannify runs. FFmpeg is licensed
under the GNU Lesser General Public License, version 2.1 or later, and LAME
under the GNU Library General Public License, version 2 or later; it is built
without any of FFmpeg's GPL-only or non-free parts. Their source code is
available from <https://ffmpeg.org> and <https://lame.sourceforge.io>, and the
exact configuration used to build the media tool is available from the author
on request.

### Not shipped

The Microsoft Edge WebView2 Runtime, which draws Dannify's window, is part of
Windows and is not distributed with Dannify.
