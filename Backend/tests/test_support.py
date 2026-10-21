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


def test_ko_fi_and_the_mpesa_till_by_default():
    out = _with()
    assert out['configured'] and out['link'] == 'https://ko-fi.com/dkavangi'
    assert out['mpesa'] == {'kind': 'till', 'number': '8496746', 'name': ''}
    assert out['paypal_link'] == 'https://www.paypal.com/ncp/payment/PLB-6P7SEVNLQBY9'


def test_an_mpesa_till_and_a_paybill():
    till = _with(mpesa={'kind': 'Till', 'number': '123 456', 'name': 'Dannify'})['mpesa']
    assert till == {'kind': 'till', 'number': '123456', 'name': 'Dannify'}
    paybill = _with(mpesa={'kind': 'paybill', 'number': '247247', 'account': '0712<script>'})['mpesa']
    assert paybill['kind'] == 'paybill' and paybill['account'] == '0712script'


def test_an_mpesa_that_is_not_one_is_left_out():
    assert _with(mpesa={'kind': 'send money', 'number': '0712345678'})['mpesa'] == {}
    assert _with(mpesa={'kind': 'till', 'number': '12'})['mpesa'] == {}
    assert _with(mpesa='0712345678')['mpesa'] == {}


def test_a_paypal_payment_link_is_kept_as_it_is():
    link = 'https://www.paypal.com/ncp/payment/PLB-6P7SEVNLQBY9'
    assert _with(paypal=link)['paypal_link'] == link
    assert _with(paypal='https://www.paypal.com.evil.example/ncp/payment/ABCD1234')['paypal_link'] == ''


def test_paypal_by_name_or_by_link():
    assert _with(paypal='dkavangi')['paypal_link'] == 'https://www.paypal.com/paypalme/dkavangi'
    assert _with(paypal='https://paypal.me/dkavangi')['paypal_link'] == 'https://www.paypal.com/paypalme/dkavangi'
    assert _with(paypal='evil.com/x?y')['paypal_link'] == ''


def test_turned_off_offers_nothing():
    out = _with(enabled=False, paypal='dkavangi', mpesa={'kind': 'till', 'number': '123456'})
    assert not out['configured'] and out['mpesa'] == {} and out['paypal_link'] == ''
