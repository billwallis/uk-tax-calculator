from __future__ import annotations

import dataclasses
import decimal
import pathlib
from typing import Any

import pytest
import yaml

HERE = pathlib.Path(__file__).parent


def to_decimal(value: Any) -> decimal.Decimal:
    """
    Return the value as a decimal.
    """
    return decimal.Decimal(str(value))


@dataclasses.dataclass
class TestCase:
    """
    A UK tax calculator test case.
    """

    salary: decimal.Decimal
    tax_year: str
    pre_tax_adjustments: decimal.Decimal
    personal_allowance: decimal.Decimal
    taxable_income: decimal.Decimal
    tax: decimal.Decimal
    national_insurance: decimal.Decimal
    other_deductions: list
    total_deductions: decimal.Decimal
    take_home_pay: decimal.Decimal

    @classmethod
    def construct(
        cls,
        loader: yaml.SafeLoader,
        node: yaml.nodes.MappingNode,
    ) -> TestCase:
        """
        Construct a test case from the data.
        """
        test_case = loader.construct_mapping(node)
        return cls(
            salary=to_decimal(test_case["salary"]),
            tax_year=test_case["tax_year"],
            pre_tax_adjustments=to_decimal(test_case["pre_tax_adjustments"]),
            personal_allowance=to_decimal(test_case["personal_allowance"]),
            taxable_income=to_decimal(test_case["taxable_income"]),
            tax=to_decimal(test_case["tax"]),
            national_insurance=to_decimal(test_case["national_insurance"]),
            # TODO: support YAML loading of sub-nodes ("other_deductions" is empty)
            other_deductions=[
                to_decimal(deduction)
                for deduction in test_case["other_deductions"]
            ],
            total_deductions=to_decimal(test_case["total_deductions"]),
            take_home_pay=to_decimal(test_case["take_home_pay"]),
        )


def get_loader() -> type[yaml.SafeLoader]:
    """
    Return a YAML loader with a custom constructor for ``TestCase``s.
    """
    loader = yaml.SafeLoader
    loader.add_constructor(
        "!TestCase",
        TestCase.construct,
    )

    return loader


def test_cases() -> list[TestCase]:
    """
    Return the test cases from the YAML file.
    """
    with open(HERE / "test-cases.yaml") as f:
        return yaml.load(f, Loader=get_loader())["test-cases"]  # noqa: S506


@pytest.fixture(params=test_cases())
def test_case(request) -> TestCase:
    """
    Return a test case.
    """
    return request.param
