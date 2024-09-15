"""
Unit tests for the ``uk_tax_calculator`` package.

Test cases can be generated from:

- https://www.tax.service.gov.uk/estimate-paye-take-home-pay
"""
import decimal
import math

import pytest

import uk_tax_calculator
from uk_tax_calculator import calculator

ZERO = decimal.Decimal(0)


@pytest.mark.parametrize(
    "value, checkpoints, expected",
    [
        (10, [1, 2, 3], [1, 1, 1, 7]),
        (5, [1, 1, 1], [1, 0, 0, 4]),
        (10, [4, 4, 4], [4, 0, 0, 6]),
        (1, [2, 2, 2, 2, 2], [1, 0, 0, 0, 0]),
        (2, [1, 2, math.inf], [1, 1, 0]),
    ],
)
def test__values_can_be_spread_over_checkpoints(
    value: decimal.Decimal,
    checkpoints: list[decimal.Decimal],
    expected: list[decimal.Decimal],
):
    """
    Values can be spread over checkpoints.

    Note this is a naughty test on a private function.
    """
    actual = calculator._spread_over_checkpoints(value, checkpoints)
    assert actual == expected


def test__invalid_tax_year_raises_value_error():
    """
    Invalid tax year raises a ``ValueError``.
    """
    with pytest.raises(ValueError):
        uk_tax_calculator.calculate_tax("bad-year", ZERO, ZERO)


def test__tax_is_correctly_calculated(test_case):
    """
    Tax is correctly calculated.
    """
    result = uk_tax_calculator.calculate_tax(
        test_case.tax_year,
        test_case.salary,
        test_case.pre_tax_adjustments,
    )

    assert result.salary == test_case.salary
    assert result.tax_year == test_case.tax_year
    assert result.pre_tax_adjustments == test_case.pre_tax_adjustments
    assert result.personal_allowance == test_case.personal_allowance
    assert result.taxable_income == test_case.taxable_income
    assert result.tax == test_case.tax
    assert result.national_insurance == test_case.national_insurance
    assert result.other_deductions == test_case.other_deductions
    assert result.total_deductions == test_case.total_deductions
    assert result.take_home_pay == test_case.take_home_pay
