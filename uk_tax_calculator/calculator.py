"""
Calculator for UK tax.

Tax bands and rates can be found at:

- https://www.gov.uk/income-tax-rates
"""

from __future__ import annotations

import dataclasses
import decimal
import enum
import itertools
import pathlib

import duckdb

HERE = pathlib.Path(__file__).parent
ZERO = decimal.Decimal(0)
PENCE = decimal.Decimal("0.01")

# TODO: Add these to the config since they can change per year
TAX_BASIC_RATE = decimal.Decimal(0.2)
TAX_HIGHER_RATE = decimal.Decimal(0.4)
TAX_ADDITIONAL_RATE = decimal.Decimal(0.45)
NI_BASIC_RATE = decimal.Decimal(0.08)
NI_ADDITIONAL_RATE = decimal.Decimal(0.02)


class TaxYear(enum.StrEnum):
    """
    UK tax years.
    """

    _2019_2020 = "2019/2020"
    _2020_2021 = "2020/2021"
    _2021_2022 = "2021/2022"
    _2022_2023 = "2022/2023"
    _2023_2024 = "2023/2024"
    _2024_2025 = "2024/2025"


@dataclasses.dataclass
class Deduction:
    """
    An additional salary deduction.
    """

    name: str
    amount: decimal.Decimal


@dataclasses.dataclass
class NetIncome:
    """
    Net income.
    """

    salary: decimal.Decimal
    tax_year: TaxYear
    pre_tax_adjustments: decimal.Decimal
    taxable_income: decimal.Decimal
    personal_allowance: decimal.Decimal
    tax: decimal.Decimal
    national_insurance: decimal.Decimal
    other_deductions: [Deduction]
    total_deductions: decimal.Decimal
    take_home_pay: decimal.Decimal

    def __post_init__(self):
        """
        Round all values to the nearest penny.
        """
        self.salary = self.salary.quantize(PENCE)
        self.pre_tax_adjustments = self.pre_tax_adjustments.quantize(PENCE)
        self.taxable_income = self.taxable_income.quantize(PENCE)
        self.personal_allowance = self.personal_allowance.quantize(PENCE)
        self.tax = self.tax.quantize(PENCE)
        self.national_insurance = self.national_insurance.quantize(PENCE)
        self.other_deductions = [
            Deduction(deduction.name, deduction.amount.quantize(PENCE))
            for deduction in self.other_deductions
        ]
        self.total_deductions = self.total_deductions.quantize(PENCE)
        self.take_home_pay = self.take_home_pay.quantize(PENCE)


@dataclasses.dataclass
class TaxBands:
    """
    Tax bands for a given tax year.
    """

    personal_allowance: decimal.Decimal
    income_limit_for_personal_allowance: decimal.Decimal
    tax_basic_rate_limit: decimal.Decimal
    tax_higher_rate_limit: decimal.Decimal
    ni_primary_threshold: decimal.Decimal
    ni_upper_earnings_limit: decimal.Decimal

    @classmethod
    def from_tax_year(cls, tax_year: str) -> TaxBands:
        """
        Create a tax band from the tax year.
        """
        tax_bands = duckdb.sql(
            f"""
            select
                personal_allowance,
                income_limit_for_personal_allowance,
                tax_basic_rate,
                tax_higher_rate,
                ni_primary_threshold * 52,
                ni_upper_earnings_limit * 52,
            from '{HERE.absolute()}/tax-bands.csv'
            where tax_year = $tax_year
            """,
            params={"tax_year": tax_year},
        ).fetchall()

        return cls(*(decimal.Decimal(v) for v in tax_bands[0]))


def calculate_tax(
    tax_year: str,
    salary: decimal.Decimal,
    pre_tax_adjustments: decimal.Decimal,
) -> NetIncome:
    """
    Calculate tax and net income.

    :param salary: The annual salary before tax and deductions.
    :param tax_year: The tax year.
    :param pre_tax_adjustments: The total of all pre-tax adjustments (yearly).
    """
    if tax_year not in iter(TaxYear):
        raise ValueError(f"Unknown tax year: {tax_year}")

    tax_bands = TaxBands.from_tax_year(tax_year)
    salary_less_adjustments = salary - pre_tax_adjustments
    personal_allowance = _calculate_personal_allowance(
        salary_less_adjustments,
        tax_bands.personal_allowance,
        tax_bands.income_limit_for_personal_allowance,
    )
    tax = _calculate_contributions(
        contributing_amount=salary_less_adjustments,
        checkpoints=[
            personal_allowance,
            tax_bands.tax_basic_rate_limit,
            tax_bands.tax_higher_rate_limit,
        ],
        rates=[ZERO, TAX_BASIC_RATE, TAX_HIGHER_RATE, TAX_ADDITIONAL_RATE],
    )
    national_insurance = _calculate_contributions(
        contributing_amount=salary,
        checkpoints=[
            tax_bands.ni_primary_threshold,
            tax_bands.ni_upper_earnings_limit,
        ],
        rates=[ZERO, NI_BASIC_RATE, NI_ADDITIONAL_RATE],
    )
    total_deductions = tax + national_insurance
    take_home_pay = salary_less_adjustments - total_deductions

    return NetIncome(
        salary=salary,
        tax_year=TaxYear(tax_year),
        pre_tax_adjustments=pre_tax_adjustments,
        personal_allowance=personal_allowance,
        taxable_income=salary_less_adjustments - personal_allowance,
        tax=tax,
        national_insurance=national_insurance,
        other_deductions=[],
        total_deductions=total_deductions,
        take_home_pay=take_home_pay,
    )


def _spread_over_checkpoints(
    value_to_spread: decimal.Decimal,
    checkpoints: list[decimal.Decimal],
) -> list[decimal.Decimal]:
    """
    Spread a value over a list of checkpoints.

    For example, the value 10 spread over the checkpoints [1, 3, 5] would
    return [1, 2, 2, 5] as:

    - 1 spreads into the first checkpoint
    - 2 spreads into the second checkpoint (the difference between 1 and 3)
    - 2 spreads into the third checkpoint (the difference between 3 and 5)
    - 5 is leftover

    :param value_to_spread: The value to spread.
    :param checkpoints: The checkpoints to spread the value over.
    """
    spread_values = []
    for interval in itertools.pairwise([ZERO, *checkpoints]):
        spread_value = min(value_to_spread, interval[1] - interval[0])
        spread_values.append(spread_value)
        value_to_spread -= spread_value

    if value_to_spread > ZERO:
        spread_values.append(value_to_spread)

    return spread_values


def _calculate_contributions(
    contributing_amount: decimal.Decimal,
    checkpoints: list[decimal.Decimal],
    rates: list[decimal.Decimal],
) -> decimal.Decimal:
    """
    Calculate the contributions based on the checkpoints and rates.

    :param contributing_amount: The amount to calculate the contributions for.
    :param checkpoints: The checkpoints for the rates.
    :param rates: The rates for the intervals between checkpoints.
    """

    amounts = _spread_over_checkpoints(
        contributing_amount,
        checkpoints,
    )

    return sum(
        (amount * rate for amount, rate in zip(amounts, rates)),
        start=ZERO,
    )


def _calculate_personal_allowance(
    taxable_income: decimal.Decimal,
    personal_allowance_lower_limit: decimal.Decimal,
    personal_allowance_upper_limit: decimal.Decimal,
) -> decimal.Decimal:
    """
    Return the personal allowance for the taxable income.

    :param taxable_income: The taxable income.
    :param personal_allowance_lower_limit: The income amount which is not
        taxed.
    :param personal_allowance_upper_limit: The income amount over which
        personal allowance decreases.
    """
    if taxable_income <= personal_allowance_lower_limit:
        return taxable_income

    return max(
        ZERO,
        personal_allowance_lower_limit
        - (max(taxable_income - personal_allowance_upper_limit, ZERO) / 2),
    )
