"""Currency handling for invoices.

Live daily exchange rates come from the free fawazahmed0 currency-api (the same source the
currency_convertor project uses), so every currency that API provides is supported.
Rates are cached for an hour. If the API is unreachable, a small fixed table keeps the common
currencies working offline. Accounting and the 50,000 INR approval rule always work in INR.
"""
import threading
import time
from typing import Any

import httpx

# CDN first, then the Cloudflare mirror (the API author recommends always having a fallback).
HOSTS = (
    "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/{path}.min.json",
    "https://latest.currency-api.pages.dev/v1/{path}.min.json",
)
CACHE_SECONDS = 3600
OUTAGE_BACKOFF_SECONDS = 60  # after a total network failure, skip the network for a minute
TIMEOUT_SECONDS = 3.0

# Offline fallback only (INR per 1 unit). Fixed demo values.
FALLBACK_INR_PER_UNIT: dict[str, float] = {"INR": 1.0, "USD": 83.0, "EUR": 90.0, "GBP": 105.0, "AED": 22.6}
FALLBACK_NAMES: dict[str, str] = {
    "INR": "Indian Rupee", "USD": "United States Dollar", "EUR": "Euro",
    "GBP": "British Pound Sterling", "AED": "United Arab Emirates Dirham",
}

_cache: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()
_down_until = 0.0


def _fetch(path: str) -> Any:
    """GET one currency-api document (cached). Raises RuntimeError if it cannot be fetched."""
    global _down_until
    now = time.time()
    with _lock:
        hit = _cache.get(path)
        if hit and now - hit[0] < CACHE_SECONDS:
            return hit[1]
        if now < _down_until:
            raise RuntimeError("currency API temporarily unreachable")
    reached_server = False
    for host in HOSTS:
        try:
            response = httpx.get(host.format(path=path), timeout=TIMEOUT_SECONDS, follow_redirects=True)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError:
            reached_server = True  # the server answered (e.g. 404): not an outage
            continue
        except (httpx.HTTPError, ValueError):
            continue
        with _lock:
            _cache[path] = (time.time(), data)
        return data
    if not reached_server:
        with _lock:
            _down_until = time.time() + OUTAGE_BACKOFF_SECONDS
    raise RuntimeError(f"currency API could not provide {path}")


def list_currencies() -> dict[str, str]:
    """Every currency the API provides as {CODE: name}; a small built-in set if it is unreachable."""
    try:
        data = _fetch("currencies")
        names = {str(code).upper(): (str(name).strip() or str(code).upper()) for code, name in data.items()}
        if names:
            return names
    except (RuntimeError, AttributeError):
        pass
    return dict(FALLBACK_NAMES)


# Common symbols and words people type instead of a code. Ambiguous ones get the usual default
# (¥ -> JPY, $ -> USD, pound -> GBP). Anything else is matched against the API's own currency names.
_SYMBOLS = {
    "$": "USD", "us$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "￥": "JPY", "円": "JPY", "₹": "INR",
    "rs": "INR", "rs.": "INR", "₩": "KRW", "₽": "RUB", "₺": "TRY", "₫": "VND", "₪": "ILS", "₦": "NGN",
    "₱": "PHP", "฿": "THB", "₴": "UAH", "₸": "KZT", "₿": "BTC", "zł": "PLN", "kč": "CZK",
    "r$": "BRL", "a$": "AUD", "c$": "CAD", "nz$": "NZD", "hk$": "HKD", "s$": "SGD",
}
_ALIASES = {
    "dollar": "USD", "dollars": "USD", "us dollar": "USD", "euro": "EUR", "euros": "EUR",
    "pound": "GBP", "pounds": "GBP", "sterling": "GBP", "yen": "JPY", "yuan": "CNY", "renminbi": "CNY",
    "rmb": "CNY", "rupee": "INR", "rupees": "INR", "dirham": "AED", "dirhams": "AED", "won": "KRW",
    "franc": "CHF", "francs": "CHF", "ruble": "RUB", "rouble": "RUB", "real": "BRL", "reais": "BRL",
}


def normalize_currency(value: str | None) -> str:
    """Resolve a code (usd), symbol ($, ¥, €) or name (yen, Japanese Yen) to a supported code.

    Empty input means INR. Raises ValueError if it cannot be resolved."""
    text = (value or "").strip()
    if not text:
        return "INR"
    supported = list_currencies()
    if text.upper() in supported:
        return text.upper()
    key = text.lower()
    guess = _SYMBOLS.get(key) or _ALIASES.get(key)
    if guess is None:
        matches = [code for code, name in supported.items() if name.lower() == key]
        if not matches:
            matches = [code for code, name in supported.items() if key in name.lower().split()]
        guess = matches[0] if len(matches) == 1 else None
    if guess and guess in supported:
        return guess
    hint = " (live currency list unreachable; only the offline set is available)" if len(supported) <= len(FALLBACK_NAMES) else ""
    raise ValueError(f"Unknown currency '{text}'. Use a currency code (USD), symbol ($) or name (yen){hint}")


def get_rate(currency: str) -> dict[str, Any]:
    """INR per 1 unit of `currency`: {"rate", "date", "source"}; source is live, fallback or fixed."""
    code = currency.upper()
    if code == "INR":
        return {"rate": 1.0, "date": None, "source": "fixed"}
    key = code.lower()
    try:
        data = _fetch(f"currencies/{key}")
        rate = float(data[key]["inr"])
        if rate > 0:
            return {"rate": rate, "date": data.get("date"), "source": "live"}
    except (RuntimeError, KeyError, TypeError, ValueError):
        pass
    if code in FALLBACK_INR_PER_UNIT:
        return {"rate": FALLBACK_INR_PER_UNIT[code], "date": None, "source": "fallback"}
    raise ValueError(f"No exchange rate for {code} is available right now; try again or use another currency")


def convert_to_inr(amount: int, currency: str) -> tuple[int, dict[str, Any]]:
    """Convert a whole amount to whole INR; also returns the rate info that was used."""
    info = get_rate(currency)
    return round(amount * info["rate"]), info


def to_inr(amount: int, currency: str) -> int:
    return convert_to_inr(amount, currency)[0]


def inr_fields(amount: int, currency: str) -> dict[str, Any]:
    """INR equivalent of an invoice amount, plus the rate details used (rate fields only if not INR)."""
    inr, info = convert_to_inr(amount, currency)
    fields: dict[str, Any] = {"amount_inr": inr}
    if currency != "INR":
        fields.update({"fx_rate": info["rate"], "fx_date": info["date"], "fx_source": info["source"]})
    return fields


def inr_value(invoice: dict[str, Any]) -> int:
    """INR equivalent of an invoice row (older INR rows have no amount_inr)."""
    return int(invoice.get("amount_inr", invoice.get("amount", 0)))
