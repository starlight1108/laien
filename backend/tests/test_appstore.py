"""App Store URL 解析测试。"""
import pytest

from app.services.appstore import AppStoreError, parse_app_url


def test_parse_valid_us_url():
    app_id, country = parse_app_url(
        "https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684"
    )
    assert app_id == "839285684"
    assert country == "us"


def test_parse_other_country_url():
    app_id, country = parse_app_url(
        "https://apps.apple.com/gb/app/some-app/id123456789"
    )
    assert app_id == "123456789"
    assert country == "gb"


def test_parse_no_country_defaults_us():
    app_id, country = parse_app_url("https://apps.apple.com/app/x/id999999")
    assert app_id == "999999"
    assert country == "us"


def test_parse_invalid_url():
    with pytest.raises(AppStoreError):
        parse_app_url("https://example.com/not-an-app-store")
    with pytest.raises(AppStoreError):
        parse_app_url("https://apps.apple.com/us/app/no-id-here")
