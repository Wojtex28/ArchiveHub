"""ETAP 13: daty zdjęć wpisywane po ludzku."""

import datetime

import pytest

from albums.dates import DateError, PhotoDate, parse_date


@pytest.mark.parametrize(
    ("text", "shown", "start", "end"),
    [
        ("1965", "1965", 1965, 1965),
        ("  1965 ", "1965", 1965, 1965),
        ("ok. 1965", "ok. 1965", 1963, 1967),
        ("ok 1965", "ok. 1965", 1963, 1967),
        ("około 1965", "ok. 1965", 1963, 1967),
        ("~1965", "ok. 1965", 1963, 1967),
        ("Ok. 1965", "ok. 1965", 1963, 1967),
        ("1965-1968", "1965–1968", 1965, 1968),
        ("1965 – 1968", "1965–1968", 1965, 1968),
        ("1965-68", "1965–1968", 1965, 1968),
        ("1965-1965", "1965", 1965, 1965),
        ("lata 60.", "lata 60.", 1960, 1969),
        ("lata 60", "lata 60.", 1960, 1969),
        ("Lata 60-te", "lata 60.", 1960, 1969),
        ("lata 1950.", "lata 50.", 1950, 1959),
        ("ok. lata 60.", "ok. lata 60.", 1958, 1971),
        ("lato 1965", "lato 1965", 1965, 1965),
        ("zimą 1970", "zima 1970", 1970, 1970),
        ("czerwiec 1965", "czerwiec 1965", 1965, 1965),
        ("czerwca 1965", "czerwiec 1965", 1965, 1965),
        ("Październik 1970", "październik 1970", 1970, 1970),
        ("06.1965", "06.1965", 1965, 1965),
        ("6/1965", "06.1965", 1965, 1965),
        ("1965-06", "06.1965", 1965, 1965),
        ("12.06.1965", "12.06.1965", 1965, 1965),
        ("1.6.1965", "01.06.1965", 1965, 1965),
        ("1965-06-12", "12.06.1965", 1965, 1965),
        ("12 czerwca 1965", "12.06.1965", 1965, 1965),
    ],
)
def test_understood_dates(text, shown, start, end):
    assert parse_date(text) == PhotoDate(shown, start, end)


def test_empty_date_is_no_date():
    assert parse_date("") == PhotoDate()
    assert not parse_date("   ")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("dawno temu", "Nie rozumiem"),
        ("ok.", "Po „ok.” wpisz rok"),
        ("1968-1965", "wcześniejszy"),
        ("31.02.1965", "nie istnieje"),
        ("13.1965", "Miesiąc 13"),
        ("1765", "pomyłkę"),
        (str(datetime.date.today().year + 1), "pomyłkę"),
        ("lata 65", "dziesięciolecie"),
        ("blabla 1965", "Nie rozumiem"),
    ],
)
def test_rejected_dates_explain_why(text, message):
    with pytest.raises(DateError, match=message):
        parse_date(text)


def test_approximate_range_does_not_go_into_the_future():
    this_year = datetime.date.today().year
    assert parse_date(f"ok. {this_year}").year_to == this_year
