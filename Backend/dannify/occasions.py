"""Special days, when Dannify dresses up a little: snow at Christmas,
confetti for the New Year.

The same days the window (frontend/src/model/occasions.js) and the installer
(installer/UI/Season.cs) use; each is tested against these dates. Here they
are for the splash, the moment the app opens.
"""

from __future__ import annotations

import datetime
import random
from typing import Optional

# (id, first day, last day) as (month, day), the last day included. A span
# may run over the year's end.
OCCASIONS = (
    ('christmas', (12, 18), (12, 26)),
    ('newyear', (12, 31), (1, 2)),
)


def today(now: Optional[datetime.date] = None) -> str:
    """The occasion on *now* (today), or ''."""

    day = now or datetime.date.today()
    md = (day.month, day.day)
    for name, start, end in OCCASIONS:
        if (start <= md <= end) if start <= end else (md >= start or md <= end):
            return name
    return ''


_HINTS = {
    'christmas': 'Merry Christmas · starting your music…',
    'newyear': 'Happy New Year · starting your music…',
}
_CONFETTI = ('#1db954', '#ffd166', '#ef476f', '#118ab2', '#c77dff')


def splash_extras(now: Optional[datetime.date] = None, seed: Optional[int] = None) -> tuple[str, str, str]:
    """(hint, css, markup) for the splash on a special day; three '' on any other.

    Drawn with CSS alone, and not at all for anyone who asked the system for
    less motion.
    """

    name = today(now)
    if not name:
        return '', '', ''
    rng = random.Random(seed)
    pieces = []
    for _ in range(22 if name == 'christmas' else 26):
        left = rng.uniform(0, 100)
        delay = -rng.uniform(0, 9)
        duration = rng.uniform(6, 11)
        if name == 'christmas':
            size = rng.uniform(3, 7)
            style = f'left:{left:.1f}%;width:{size:.1f}px;height:{size:.1f}px;'
        else:
            color = _CONFETTI[rng.randrange(len(_CONFETTI))]
            style = f'left:{left:.1f}%;width:6px;height:10px;background:{color};border-radius:1px;'
        pieces.append(f"<i class='f' style='{style}animation-delay:{delay:.1f}s;animation-duration:{duration:.1f}s'></i>")
    spin = ' rotate(540deg)' if name == 'newyear' else ''
    css = (
        '.fx{position:fixed;inset:0;pointer-events:none;overflow:hidden}'
        '.f{position:absolute;top:-12px;border-radius:50%;background:#fff;opacity:.75;'
        'animation:fall linear infinite}'
        f'@keyframes fall{{to{{transform:translateY(110vh){spin}}}}}'
        '@media (prefers-reduced-motion:reduce){.fx{display:none}}'
    )
    return _HINTS[name], css, "<div class='fx' aria-hidden='true'>" + ''.join(pieces) + '</div>'
