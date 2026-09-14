from datetime import date

from scpi.parsing import (
    parse_date_fr,
    parse_number_fr,
    parse_period_quarter,
    quarter_end_date,
)


def test_parse_number_fr_thousands_and_decimal():
    assert parse_number_fr("1 234,56 €") == 1234.56
    assert parse_number_fr("Prix : 1 135 €") == 1135.0
    assert parse_number_fr("6,05 %") == 6.05
    assert parse_number_fr("1 084,02 M€") == 1084.02


def test_parse_number_fr_none_when_absent():
    assert parse_number_fr("aucun chiffre ici") is None
    assert parse_number_fr("") is None


def test_parse_period_quarter_both_orders():
    assert parse_period_quarter("CORUM XL - Fil d'Actualités 2026-T2.pdf") == (2026, 2)
    assert parse_period_quarter("Bulletin T3 2025") == (2025, 3)
    assert parse_period_quarter("rien") is None


def test_quarter_end_date():
    assert quarter_end_date(2026, 2) == date(2026, 6, 30)
    assert quarter_end_date(2025, 4) == date(2025, 12, 31)


def test_parse_date_fr():
    assert parse_date_fr("au 15/04/2025") == date(2025, 4, 15)
    assert parse_date_fr("le 1 janvier 2025") == date(2025, 1, 1)
    assert parse_date_fr("date inconnue") is None
