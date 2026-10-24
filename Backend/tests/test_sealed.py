"""Sealed logs: a shipped copy's log can be read by the developer only."""

from __future__ import annotations

import os

import pytest

from dannify import logsetup, report, sealed


def test_x25519_is_rfc_7748():
    scalar = bytes.fromhex('a546e36bf0527c9d3b16154b82465edd62144c0ac1fc5a18506a2244ba449ac4')
    point = bytes.fromhex('e6db6867583030db3594c1a424b15f7c726624ec26b3353b10a903a6d0ab1c4c')
    assert sealed.x25519(scalar, point).hex() == 'c3da55379de9c6908e94ea4df28d084f32eccf03491c71f754b4075577a28552'
    # Two sides of an exchange agree.
    a, b = os.urandom(32), os.urandom(32)
    assert sealed.x25519(a, sealed.public_of(b)) == sealed.x25519(b, sealed.public_of(a))


def test_a_sealed_line_opens_with_the_private_key_only():
    private = os.urandom(32)
    sealer = sealed.Sealer(sealed.public_of(private))
    text = '2026-10-24 05:43 ✗ ERROR explorer   search failed for "Sauti Sol"\nTraceback ...'
    line = sealer.seal(text)
    assert sealed.is_sealed(line) and '\n' not in line and 'explorer' not in line
    assert sealed.Opener(private).open(line) == text
    # Another key opens nothing, and a changed letter is caught.
    assert sealed.Opener(os.urandom(32)).open(line) is None
    flipped = line[:-5] + ('A' if line[-5] != 'A' else 'B') + line[-4:]
    assert sealed.Opener(private).open(flipped) is None
    # Each line carries what opens it: lines of two runs read together.
    other = sealed.Sealer(sealed.public_of(private)).seal('the next run')
    text_out = sealed.Opener(private).read('\n'.join([line, '[desktop] plain', other]))
    assert text_out.splitlines()[-2:] == ['[desktop] plain', 'the next run']


def test_shipped_copies_always_seal(monkeypatch):
    monkeypatch.delenv('DANNIFY_SEAL_LOGS', raising=False)
    monkeypatch.delattr('sys.frozen', raising=False)
    assert not sealed.sealing()
    monkeypatch.setenv('DANNIFY_SEAL_LOGS', '1')
    assert sealed.sealing()
    monkeypatch.setattr('sys.frozen', True, raising=False)
    monkeypatch.setenv('DANNIFY_SEAL_LOGS', '0')
    assert sealed.sealing(), 'no setting turns it off in a shipped copy'


def test_the_log_file_is_sealed_scrubbed_and_turned_over(tmp_path, monkeypatch):
    monkeypatch.setenv('DANNIFY_SEAL_LOGS', '1')
    private = os.urandom(32)
    monkeypatch.setattr(sealed, '_sealer', sealed.Sealer(sealed.public_of(private)))
    path = tmp_path / 'dannify.log'
    sink = logsetup._SealedFile(path, limit=800, keep=2)
    for n in range(30):
        sink(f'line {n} token=abc123secret\n')
    files = sorted(p.name for p in tmp_path.iterdir())
    assert files == ['dannify.log', 'dannify.log.1', 'dannify.log.2']
    raw = path.read_text(encoding='utf-8')
    assert 'line' not in raw and 'abc123' not in raw
    opened = sealed.Opener(private).read(raw)
    assert 'line 29 token=<removed>' in opened and 'abc123' not in opened


def test_a_report_says_a_sealed_log_is_sealed(tmp_path, monkeypatch):
    monkeypatch.setenv('DANNIFY_SEAL_LOGS', '1')
    monkeypatch.setattr(sealed, '_sealer', None)
    log = tmp_path / 'dannify.log'
    log.write_text('\n'.join(sealed.line(f'record {n}') for n in range(5)) + '\n', encoding='utf-8')
    out = report.preview(tmp_path, '4.15.0')
    assert out['logs_sealed'] is True and out['logs_tail'] == ''
    assert 'Python' not in out['about'] and 'Core:' in out['about']


@pytest.mark.parametrize('line', ['', '~short', 'plain text line', '~' + 'a' * 80 + ' b'])
def test_plain_lines_are_not_taken_for_sealed_ones(line):
    assert not sealed.is_sealed(line)


def test_the_linux_package_seals_and_a_test_reads_with_a_key_of_its_own(tmp_path, monkeypatch):
    monkeypatch.delenv('DANNIFY_SEAL_LOGS', raising=False)
    monkeypatch.delattr('sys.frozen', raising=False)
    monkeypatch.setenv('DANNIFY_PACKAGED', '1')  # what /usr/bin/dannify sets
    assert sealed.sealing()
    own = os.urandom(32)
    monkeypatch.setenv('DANNIFY_LOG_KEY', sealed.public_of(own).hex())
    monkeypatch.setattr(sealed, '_sealer', None)
    line = sealed.line('Application startup complete')
    assert sealed.is_sealed(line) and 'startup' not in line
    assert sealed.Opener(own).open(line) == 'Application startup complete'
    # Anything that is not a key leaves it sealed for the developer.
    monkeypatch.setenv('DANNIFY_LOG_KEY', 'plain please')
    assert sealed._public().hex() == sealed.LOG_PUBLIC
