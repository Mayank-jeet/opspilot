"""Small Playwright adapter for the local simulated company applications."""

import os
from typing import Any

# The agent's browser calls the app's own simulated pages. On Render the app listens on $PORT.
BASE_URL = os.getenv("INTERNAL_BASE_URL") or f"http://127.0.0.1:{os.getenv('PORT', '8000')}"

# Docker's shared memory is tiny; without --disable-dev-shm-usage Chromium often crashes.
CHROMIUM_ARGS = ["--disable-dev-shm-usage", "--disable-gpu"]


def _playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is not installed. Install backend requirements and run 'playwright install chromium'.") from exc
    return sync_playwright


def open_accounting_page() -> str:
    with _playwright()() as playwright:
        browser = playwright.chromium.launch(headless=True, args=CHROMIUM_ARGS)
        try:
            page = browser.new_page()
            page.goto(f"{BASE_URL}/simulated/accounting", wait_until="domcontentloaded")
            return page.get_by_role("heading", name="Accounting").inner_text()
        finally:
            browser.close()


def fill_invoice_form(invoice: dict[str, Any]) -> str:
    with _playwright()() as playwright:
        browser = playwright.chromium.launch(headless=True, args=CHROMIUM_ARGS)
        try:
            page = browser.new_page()
            page.goto(f"{BASE_URL}/simulated/accounting", wait_until="domcontentloaded")
            page.locator("#invoice_number").fill(str(invoice["invoice_number"]))
            page.locator("#vendor").fill(str(invoice["vendor"]))
            page.locator("#amount").fill(str(invoice["amount"]))
            page.locator("#currency").fill(str(invoice.get("currency", "INR")))
            page.locator("#due_date").fill(str(invoice["due_date"]))
            return page.locator("#invoice_number").input_value()
        finally:
            browser.close()


def submit_invoice_form(invoice: dict[str, Any]) -> dict[str, Any]:
    with _playwright()() as playwright:
        browser = playwright.chromium.launch(headless=True, args=CHROMIUM_ARGS)
        try:
            page = browser.new_page()
            page.goto(f"{BASE_URL}/simulated/accounting", wait_until="domcontentloaded")
            page.locator("#invoice_number").fill(str(invoice["invoice_number"]))
            page.locator("#vendor").fill(str(invoice["vendor"]))
            page.locator("#amount").fill(str(invoice["amount"]))
            page.locator("#currency").fill(str(invoice.get("currency", "INR")))
            page.locator("#due_date").fill(str(invoice["due_date"]))
            page.get_by_role("button", name="Submit invoice").click()
            page.wait_for_function("document.querySelector('#submission-result').textContent.trim().length > 0")
            result = page.locator("#submission-result").inner_text()
            status = page.locator("#submission-result").get_attribute("data-status")
            if status != "success":
                raise RuntimeError(result or "Accounting rejected the invoice")
            invoice_number, record_status = result.split(" — ", maxsplit=1)
            return {"invoice_number": invoice_number, "status": record_status}
        finally:
            browser.close()
