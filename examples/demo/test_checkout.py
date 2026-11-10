"""Illustrative tests supplied as text to the review agent, never run by it."""

from checkout import average_order_value


def test_average_order_value():
    assert average_order_value([10, 20]) == 15
