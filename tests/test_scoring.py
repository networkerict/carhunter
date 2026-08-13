from types import SimpleNamespace

import pytest

from scoring import calculate_car_score, calculate_value_score


def car(**overrides):
    values = {
        "title": "Audi A6",
        "description": "",
        "options_found": "",
        "year": None,
        "km": None,
        "price": 50_000,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_calculate_car_score_missing_km_gets_no_kilometer_bonus():
    assert calculate_car_score(car()) == 0


@pytest.mark.parametrize(
    ("km", "expected_score"),
    [(19_999, 10), (20_000, 5), (39_999, 5), (40_000, 0)],
)
def test_calculate_car_score_preserves_kilometer_boundaries(km, expected_score):
    assert calculate_car_score(car(km=km)) == expected_score


def test_calculate_value_score_missing_km_keeps_base_and_price_score():
    score, breakdown = calculate_value_score(car(km=None, price=39_999), explain=True)

    assert score == 70
    assert [item["reason"] for item in breakdown] == [
        "Basis waarde score",
        "Prijs < €40.000",
    ]


@pytest.mark.parametrize(
    ("km", "expected_score"),
    [(29_999, 65), (30_000, 60), (49_999, 60), (50_000, 50)],
)
def test_calculate_value_score_preserves_kilometer_boundaries(km, expected_score):
    assert calculate_value_score(car(km=km)) == expected_score


def test_engine_variant_in_title_takes_priority_over_description():
    subject = car(title="Audi A6 40 TFSI", description="Ook leverbaar als 45 TFSI")

    assert calculate_car_score(subject) == 15


def test_45_tfsi_is_detected_in_title():
    assert calculate_car_score(car(title="Audi A6 45 TFSI")) == 30


def test_engine_variant_falls_back_to_description():
    subject = car(title="Audi A6", description="Uitgevoerd als 45 TFSI")

    assert calculate_car_score(subject) == 30


def test_options_are_not_used_for_engine_variant_detection():
    assert calculate_car_score(car(options_found="45 TFSI")) == 0
