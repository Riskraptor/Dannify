"""Build the public site out of website/index.html.

The readable source lives here, in the private repository. What goes out is a
single squashed file with short asset names, because the public repository is
meant to carry the download and nothing else.

    python website/build.py <path-to-dannify-releases-checkout>

Anyone can still read a web page, and nothing here pretends otherwise. This
only keeps the comments, the structure and the working notes out of it.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Published name -> where the picture comes from.
ASSETS = {
    'a/d.svg': HERE.parent / 'frontend' / 'src' / 'assets' / 'dannify.svg',
    'a/i.ico': HERE.parent / 'frontend' / 'public' / 'favicon.ico',
    'a/t.png': HERE.parent / 'frontend' / 'public' / 'apple-touch-icon.png',
    'a/n.png': HERE / 'shots' / 'nowplaying.png',
    'a/h.png': HERE / 'shots' / 'home.png',
    'a/s.png': HERE / 'shots' / 'search.png',
    'a/g.png': HERE / 'shots' / 'settings.png',
    'a/m.png': HERE / 'shots' / 'mini.png',
}


def squash(html: str) -> str:
    """Flatten the page without changing what it does.

    Deliberately conservative: newlines stay inside the script so there is no
    chance of two statements running together, and only the parts that cannot
    be whitespace sensitive get collapsed.
    """

    style = re.search(r'<style>(.*?)</style>', html, re.S)
    script = re.search(r'<script>(.*?)</script>', html, re.S)
    css = style.group(1) if style else ''
    js = script.group(1) if script else ''

    # Take them out, squash the markup, then put the squashed versions back.
    if style:
        html = html.replace(style.group(0), '<style>@@CSS@@</style>')
    if script:
        html = html.replace(script.group(0), '<script>@@JS@@</script>')

    html = re.sub(r'<!--.*?-->', '', html, flags=re.S)
    html = re.sub(r'\s*\n\s*', ' ', html)
    html = re.sub(r'>\s+<', '><', html)
    html = re.sub(r'  +', ' ', html).strip()

    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    css = re.sub(r'\s*\n\s*', '', css)
    css = re.sub(r'\s*([{};:,>])\s*', r'\1', css)
    css = css.replace(';}', '}')

    # Only whole-line comments: a // inside a string or a regex must survive.
    js = '\n'.join(
        line.strip()
        for line in js.split('\n')
        if line.strip() and not line.strip().startswith('//')
    )

    return html.replace('@@CSS@@', css).replace('@@JS@@', js)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    out = Path(sys.argv[1]).resolve() / 'docs'
    if not out.parent.is_dir():
        print(f'no such checkout: {out.parent}')
        return 1

    (out / 'a').mkdir(parents=True, exist_ok=True)
    (out / '.nojekyll').write_text('', encoding='utf-8')

    missing = [str(src) for src in ASSETS.values() if not src.is_file()]
    if missing:
        print('missing source files:')
        for m in missing:
            print('   ', m)
        return 1
    for name, src in ASSETS.items():
        shutil.copy2(src, out / name)

    page = squash((HERE / 'index.html').read_text(encoding='utf-8'))
    (out / 'index.html').write_text(page, encoding='utf-8')

    raw = (HERE / 'index.html').stat().st_size
    print(f'  index.html  {raw / 1024:.0f} KB -> {len(page) / 1024:.0f} KB')
    print(f'  assets      {len(ASSETS)}')
    print(f'  into        {out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
