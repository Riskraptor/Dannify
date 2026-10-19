"""Word-by-word times from enhanced LRC files."""

from dannify.lyrics import parse_lrc


def test_plain_lines_carry_no_words():
    lines = parse_lrc('[00:01.00]Just a line\n[00:02.50]Another')
    assert lines == [
        {'time': 1.0, 'text': 'Just a line'},
        {'time': 2.5, 'text': 'Another'},
    ]


def test_word_times_are_read_and_never_shown_as_text():
    (line,) = parse_lrc('[00:10.00]<00:10.00>Hello <00:10.50>bright <00:11.20>world<00:12.00>')
    assert line['text'] == 'Hello bright world'
    assert '<' not in line['text']
    assert [w['time'] for w in line['words']] == [10.0, 10.5, 11.2]
    assert ''.join(w['text'] for w in line['words']) == 'Hello bright world'
    assert line['end'] == 12.0


def test_words_before_the_first_stamp_start_with_the_line():
    (line,) = parse_lrc('[00:05.00]Oh <00:05.60>yeah')
    assert line['words'] == [{'time': 5.0, 'text': 'Oh '}, {'time': 5.6, 'text': 'yeah'}]
    assert 'end' not in line


def test_a_chorus_stamped_twice_is_sung_the_same_way_later():
    lines = parse_lrc('[00:20.00][01:00.00]<00:20.00>Sing <00:20.75>along<00:21.50>')
    assert [line['time'] for line in lines] == [20.0, 60.0]
    assert [w['time'] for w in lines[1]['words']] == [60.0, 60.75]
    assert lines[1]['end'] == 61.5


def test_word_times_out_of_order_are_dropped_but_the_words_stay():
    (line,) = parse_lrc('[00:31.00]<00:33.00>bad <00:32.00>order')
    assert line == {'time': 31.0, 'text': 'bad order'}
