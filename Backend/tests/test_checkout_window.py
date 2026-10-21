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
    assert allowed('https://www.paypal.com/ncp/payment/PLB-6P7SEVNLQBY9')
    assert allowed('https://www.paypal.com/paypalme/dkavangi')
    for url in (
        'http://www.paypal.com/ncp/payment/PLB-6P7SEVNLQBY9',
        'https://www.paypal.com.evil.example/ncp/payment/PLB-6P7SEVNLQBY9',
        'https://evil.example/?https://www.paypal.com/ncp/payment/PLB-6P7SEVNLQBY9',
        'https://www.paypal.com/signin',
        'javascript:alert(1)',
        '',
    ):
        assert not allowed(url), url


def test_paying_is_seen_by_the_thank_you_address():
    ns = _load('RETURN_PREFIX')
    assert ns['RETURN_PREFIX'] == 'https://github.com/Riskraptor/Dannify'
