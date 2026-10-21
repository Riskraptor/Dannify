"""The window PayPal's checkout opens in: only PayPal's own pages, ever."""

import ast
import re

from tests._shell_source import windows_tree


def _load(*names: str) -> dict:
    tree = windows_tree()
    wanted = [
        node for node in tree.body
        if (isinstance(node, ast.FunctionDef) and node.name in names)
        or (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets))
    ]
    namespace: dict = {'re': re}
    exec(compile(ast.Module(body=wanted, type_ignores=[]), 'checkout.py', 'exec'), namespace)
    return namespace


def test_only_paypal_checkouts_open_in_the_window():
    allowed = _load('_ALLOWED', 'allowed')['allowed']
    assert allowed('https://www.paypal.com/ncp/payment/PLB-LCYXAHFS4UA3')
    assert allowed('https://www.paypal.com/paypalme/dkavangi')
    for url in (
        'http://www.paypal.com/ncp/payment/PLB-LCYXAHFS4UA3',
        'https://www.paypal.com.evil.example/ncp/payment/PLB-LCYXAHFS4UA3',
        'https://evil.example/?https://www.paypal.com/ncp/payment/PLB-LCYXAHFS4UA3',
        'https://www.paypal.com/signin',
        'javascript:alert(1)',
        '',
    ):
        assert not allowed(url), url


def test_paying_is_seen_by_the_thank_you_address():
    prefixes = _load('RETURN_PREFIXES')['RETURN_PREFIXES']
    assert 'https://riskraptor.github.io/Dannify/thanks/'.startswith(prefixes)
    assert 'https://github.com/Riskraptor/Dannify'.startswith(prefixes)
    assert not 'https://www.paypal.com/ncp/payment/PLB-LCYXAHFS4UA3'.startswith(prefixes)
    assert not 'https://riskraptor.github.io/Dannify/'.startswith(prefixes)


def test_the_window_always_fits_the_screen():
    bounds = _load('_dialog_bounds')['_dialog_bounds']
    # A big screen: the size asked for, in the middle.
    (x, y, w, h), smallest = bounds((0, 0, 1920, 1040), (556, 819), (436, 559), 16)
    assert (w, h) == (556, 819) and x == (1920 - 556) // 2 and y == (1040 - 819) // 2
    assert smallest == (436, 559)
    # A 1366 x 768 laptop: cut to the free area, the title bar on screen.
    (x, y, w, h), smallest = bounds((0, 0, 1366, 728), (556, 819), (436, 559), 16)
    assert h == 728 - 32 and y == 16 and y + h <= 728
    assert smallest[1] <= h
    # A second screen to the left of the first, coordinates negative.
    (x, y, w, h), _ = bounds((-1280, 0, 1280, 984), (556, 819), (436, 559), 16)
    assert -1280 <= x and x + w <= 0
    # Smaller than the smallest size: the smallest gives way.
    (_, _, w, h), smallest = bounds((0, 0, 400, 500), (556, 819), (436, 559), 16)
    assert smallest == (w, h) == (368, 468)
