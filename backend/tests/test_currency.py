import unittest
from unittest.mock import MagicMock, patch

import httpx

from app import currency


def ok(payload):
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


class CurrencyTests(unittest.TestCase):
    def setUp(self):
        currency._cache.clear()
        currency._down_until = 0.0

    def test_live_rate_is_used_and_cached(self):
        payload = {"date": "2026-10-10", "usd": {"inr": 88.5}}
        with patch("app.currency.httpx.get", return_value=ok(payload)) as get:
            first = currency.get_rate("usd")
            second = currency.get_rate("USD")
        self.assertEqual(first, {"rate": 88.5, "date": "2026-10-10", "source": "live"})
        self.assertEqual(second, first)
        self.assertEqual(get.call_count, 1)  # the second call came from the cache

    def test_mirror_is_used_when_cdn_fails(self):
        payload = {"date": "2026-10-10", "eur": {"inr": 96.0}}
        with patch("app.currency.httpx.get", side_effect=[httpx.ConnectError("down"), ok(payload)]) as get:
            self.assertEqual(currency.get_rate("eur")["source"], "live")
        self.assertIn("pages.dev", get.call_args_list[1].args[0])

    def test_falls_back_to_fixed_rate_when_api_is_down(self):
        with patch("app.currency.httpx.get", side_effect=httpx.ConnectError("down")):
            info = currency.get_rate("USD")
        self.assertEqual(info["source"], "fallback")
        self.assertEqual(info["rate"], currency.FALLBACK_INR_PER_UNIT["USD"])

    def test_currency_without_fallback_rate_raises_when_api_is_down(self):
        with patch("app.currency.httpx.get", side_effect=httpx.ConnectError("down")):
            with self.assertRaises(ValueError):
                currency.get_rate("JPY")

    def test_every_currency_from_the_api_is_accepted(self):
        listing = {"usd": "United States Dollar", "inr": "Indian Rupee", "jpy": "Japanese Yen", "btc": "Bitcoin"}
        with patch("app.currency.httpx.get", return_value=ok(listing)):
            self.assertEqual(currency.normalize_currency("jpy"), "JPY")
            self.assertEqual(currency.normalize_currency("BTC"), "BTC")
            self.assertEqual(currency.normalize_currency(None), "INR")
            with self.assertRaises(ValueError):
                currency.normalize_currency("zzz")

    def test_symbols_and_names_resolve_to_codes(self):
        listing = {"usd": "United States Dollar", "inr": "Indian Rupee", "jpy": "Japanese Yen",
                   "eur": "Euro", "gbp": "British Pound Sterling", "chf": "Swiss Franc"}
        with patch("app.currency.httpx.get", return_value=ok(listing)):
            for given, expected in (("$", "USD"), ("¥", "JPY"), ("€", "EUR"), ("£", "GBP"), ("₹", "INR"),
                                    ("yen", "JPY"), ("Japanese Yen", "JPY"), ("dollars", "USD"), ("usd", "USD"),
                                    ("franc", "CHF"), ("", "INR")):
                self.assertEqual(currency.normalize_currency(given), expected, given)
            with self.assertRaises(ValueError):
                currency.normalize_currency("monopoly money")

    def test_inr_fields_and_inr_value(self):
        info = {"rate": 88.5, "date": "2026-10-10", "source": "live"}
        with patch("app.currency.get_rate", return_value=info):
            usd = currency.inr_fields(2000, "USD")
            inr = currency.inr_fields(2000, "INR")
        self.assertEqual(usd, {"amount_inr": 177000, "fx_rate": 88.5, "fx_date": "2026-10-10", "fx_source": "live"})
        self.assertEqual(inr, {"amount_inr": 177000})  # mocked rate applies to every code here; shape is what matters
        self.assertEqual(currency.inr_value({"amount": 40000}), 40000)  # older INR rows have no amount_inr
        self.assertEqual(currency.inr_value({"amount": 700, "amount_inr": 58100}), 58100)

    def test_convert_rounds_to_whole_inr_and_returns_rate_info(self):
        info = {"rate": 88.5, "date": "2026-10-10", "source": "live"}
        with patch("app.currency.get_rate", return_value=info):
            self.assertEqual(currency.convert_to_inr(700, "USD"), (61950, info))


if __name__ == "__main__":
    unittest.main()
