"""The ways to support Dannify, as the app is told them."""

import pytest

from dannify import support


@pytest.fixture(autouse=True)
def _restore():
    kept = dict(support._config)
    yield
    support._config.clear()
    support._config.update(kept)


def _with(**values):
    support._config.clear()
    support._config.update({**support._DEFAULTS, **values})
    return support.config()


def test_github_sponsors_only_by_default():
    out = _with()
    assert out['configured'] and out['sponsors_link'] == 'https://github.com/sponsors/Riskraptor'
    # M-Pesa is gone; PayPal and Ko-fi are not offered unless set.
    assert 'mpesa' not in out
    assert out['paypal_link'] == '' and out['link'] == ''


def test_a_sponsors_account_is_a_github_name_or_nothing():
    assert _with(github='some-dev')['sponsors_link'] == 'https://github.com/sponsors/some-dev'
    for bad in ('evil.com/x', '-lead', 'trail-', 'two--hyphens', 'x' * 40, '../x', ''):
        assert _with(github=bad)['sponsors_link'] == '', bad


def test_nothing_to_give_with_from_anywhere_is_not_configured():
    assert not _with(github='', link='', paypal='')['configured']


def test_an_mpesa_number_set_anywhere_is_not_shown():
    assert 'mpesa' not in _with(mpesa={'kind': 'till', 'number': '8496746'})


def test_a_paypal_payment_link_is_kept_as_it_is():
    link = 'https://www.paypal.com/ncp/payment/PLB-WVTSZMLQNTLQ'
    assert _with(paypal=link)['paypal_link'] == link
    assert _with(paypal='https://www.paypal.com.evil.example/ncp/payment/ABCD1234')['paypal_link'] == ''


def test_paypal_by_name_or_by_link():
    assert _with(paypal='dkavangi')['paypal_link'] == 'https://www.paypal.com/paypalme/dkavangi'
    assert _with(paypal='https://paypal.me/dkavangi')['paypal_link'] == 'https://www.paypal.com/paypalme/dkavangi'
    assert _with(paypal='evil.com/x?y')['paypal_link'] == ''


def test_turned_off_offers_nothing():
    out = _with(enabled=False, paypal='dkavangi')
    assert not out['configured'] and out['paypal_link'] == ''
    assert out['sponsors_link'] == ''
