"""Release signatures, checked against the published Ed25519 test vectors."""

from __future__ import annotations

import pytest

from dannify import signing

# RFC 8032, section 7.1, TEST 1 to 3.
VECTORS = [
    (
        '9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60',
        'd75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a',
        '',
        'e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155'
        '5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b',
    ),
    (
        '4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb',
        '3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c',
        '72',
        '92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da'
        '085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00',
    ),
    (
        'c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7',
        'fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025',
        'af82',
        '6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac'
        '18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a',
    ),
]


@pytest.mark.parametrize('secret, public, message, signature', VECTORS)
def test_rfc8032_vectors(secret, public, message, signature):
    secret_b, public_b = bytes.fromhex(secret), bytes.fromhex(public)
    message_b, signature_b = bytes.fromhex(message), bytes.fromhex(signature)
    assert signing.public_key(secret_b) == public_b
    assert signing.sign(secret_b, message_b) == signature_b
    assert signing.verify(public_b, message_b, signature_b)


@pytest.mark.parametrize('secret, public, message, signature', VECTORS)
def test_anything_changed_fails(secret, public, message, signature):
    public_b, signature_b = bytes.fromhex(public), bytes.fromhex(signature)
    message_b = bytes.fromhex(message)
    assert not signing.verify(public_b, message_b + b'x', signature_b)
    flipped = bytearray(signature_b)
    flipped[5] ^= 1
    assert not signing.verify(public_b, message_b, bytes(flipped))
    other = bytes.fromhex(VECTORS[0][1] if public != VECTORS[0][1] else VECTORS[1][1])
    assert not signing.verify(other, message_b, signature_b)


def test_malformed_input_is_just_false():
    public = bytes.fromhex(VECTORS[0][1])
    assert not signing.verify(public, b'', b'short')
    assert not signing.verify(b'short', b'', bytes(64))
    assert not signing.verify(public, b'', bytes(64))
    # s >= L must be refused (signature malleability).
    sig = bytes.fromhex(VECTORS[0][3])
    big_s = sig[:32] + (b'\xff' * 32)
    assert not signing.verify(public, b'', big_s)


def test_release_statements_bind_kind_version_and_hash():
    secret = bytes.fromhex(VECTORS[1][0])
    public_hex = VECTORS[1][1]
    digest = 'ab' * 32
    sig = signing.sign(secret, signing.statement('package', '4.7.0', digest)).hex()

    assert signing.verify_release(public_hex, 'package', '4.7.0', digest, sig)
    assert signing.verify_release(public_hex, 'package', '4.7.0', digest.upper(), sig + '\n')
    assert not signing.verify_release(public_hex, 'installer', '4.7.0', digest, sig)
    assert not signing.verify_release(public_hex, 'package', '4.6.2', digest, sig)
    assert not signing.verify_release(public_hex, 'package', '4.7.0', 'cd' * 32, sig)
    assert not signing.verify_release(public_hex, 'package', '4.7.0', digest, 'not hex')
    assert not signing.verify_release(public_hex, 'package', '4.7.0', digest, '')
    assert not signing.verify_release('zz', 'package', '4.7.0', digest, sig)
    with pytest.raises(ValueError):
        signing.statement('package', '4.7.0\ninstaller', digest)
