"""Unit tests for utils module."""

import pytest
from src.utils import env, mask_key, clean_html, to_float, compact_usd


def test_mask_key():
    assert mask_key("abcdefghij1234567890") == "abcde...7890"
    assert mask_key("short") == "***"
    assert mask_key("1234567890") == "***"  # 10 chars or less returns ***
    assert mask_key("  spaces  ") == "***"  # After strip, it's short


def test_clean_html():
    assert clean_html("<p>Hello</p>") == "Hello"
    assert clean_html("<div>Test <b>bold</b></div>") == "Test bold"
    assert clean_html("&lt;script&gt;") == ""  # HTML entities are unescaped then tags removed
    assert clean_html("Multiple   spaces") == "Multiple spaces"
    assert clean_html("") == ""


def test_to_float():
    assert to_float(123) == 123.0
    assert to_float("456.78") == 456.78
    assert to_float("123") == 123.0
    assert to_float(None) is None
    assert to_float("invalid") is None
    assert to_float("") is None


def test_compact_usd():
    assert compact_usd(None) == "N/A"
    assert compact_usd(0) == "$0.00"
    assert compact_usd(500) == "$500.00"
    assert compact_usd(1_500) == "$1.50K"
    assert compact_usd(1_500_000) == "$1.50M"
    assert compact_usd(2_500_000_000) == "$2.50B"
    assert compact_usd(999) == "$999.00"
    assert compact_usd(1_000) == "$1.00K"
    assert compact_usd(999_999) == "$1000.00K"
    assert compact_usd(1_000_000) == "$1.00M"
