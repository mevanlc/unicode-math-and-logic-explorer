#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["playwright"]
# ///
"""Exercise the generated report in an isolated, offline Chrome session."""

from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parent.parent


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome")
        context = browser.new_context(
            viewport={"width": 1440, "height": 1100}, color_scheme="light"
        )
        context.set_offline(True)
        context.grant_permissions(["clipboard-read", "clipboard-write"])
        page = context.new_page()
        errors = []
        network = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: network.append(request.url))
        page.goto((ROOT / "target" / "inventory.html").as_uri())
        cards = page.locator(".symbol-card")
        search = page.get_by_role("searchbox", name="Search symbols")
        expect(cards).to_have_count(3389)
        page.locator("#group-by").select_option("all")
        numbers = cards.evaluate_all(
            "items => items.map(item => Number(item.dataset.codepoint))"
        )
        assert numbers == sorted(set(numbers))

        search.fill("conjunction")
        expect(page.locator("#symbol-8743")).to_be_visible()
        search.fill("U+2229")
        expect(cards).to_have_count(1)
        expect(page.locator(".detail-title")).to_have_text("INTERSECTION")
        page.get_by_role("button", name="Copy character", exact=True).click()
        assert page.evaluate("navigator.clipboard.readText()") == "∩"
        page.get_by_role("button", name="Copy variant: with serifs").click()
        assert page.evaluate("navigator.clipboard.readText()") == "∩\ufe00"

        # Exercise the file:// fallback using the real browser clipboard.
        page.evaluate(
            "window.savedClipboard = navigator.clipboard; Object.defineProperty(navigator, 'clipboard', {value: undefined, configurable: true})"
        )
        page.get_by_role("button", name="Copy character", exact=True).click()
        assert page.evaluate("window.savedClipboard.readText()") == "∩"
        page.evaluate("delete navigator.clipboard; delete window.savedClipboard")

        search.fill("∩\ufe00")
        expect(cards).to_have_count(1)
        expect(page.locator(".detail-title")).to_have_text("INTERSECTION")
        page.locator(".reference").filter(has_text="N-ARY INTERSECTION").click()
        expect(page.locator(".detail-title")).to_have_text("N-ARY INTERSECTION")

        for query in ["𝐀", "U+1D400", "0x1d400", "1D400"]:
            search.fill(query)
            expect(cards).to_have_count(1)
            expect(page.locator(".detail-title")).to_have_text(
                "MATHEMATICAL BOLD CAPITAL A"
            )
        page.get_by_role("button", name="Copy character", exact=True).click()
        assert page.evaluate("navigator.clipboard.readText()") == "𝐀"

        search.fill("U+20D7")
        expect(page.locator(".detail-title")).to_have_text(
            "COMBINING RIGHT ARROW ABOVE"
        )
        expect(page.locator(".detail-preview")).to_have_text("◌⃗")
        page.get_by_role("button", name="Copy character", exact=True).click()
        assert page.evaluate("navigator.clipboard.readText()") == "\u20d7"
        search.fill("U+2062")
        expect(page.locator(".detail-title")).to_have_text("INVISIBLE TIMES")
        expect(page.locator(".detail-preview")).to_have_text("invisible")
        page.get_by_role("button", name="Copy character", exact=True).click()
        assert page.evaluate("navigator.clipboard.readText()") == "\u2062"

        page.get_by_role("button", name="Reset filters").click()
        page.locator("#pool").select_option("math")
        expect(cards).to_have_count(2322)
        page.locator("#pool").select_option("additional")
        expect(cards).to_have_count(1067)
        page.locator("#pool").select_option("all")
        page.locator("#letters").select_option("hide")
        expect(cards).to_have_count(2192)
        page.locator("#letters").select_option("only")
        expect(cards).to_have_count(1197)
        page.get_by_role("button", name="Reset filters").click()
        page.locator("#script").select_option("Greek")
        expect(cards).to_have_count(59)

        page.get_by_role("button", name="Reset filters").click()
        page.locator("#group-by").select_option("subheading")
        page.locator("#group-filter").select_option("Matrix ellipses")
        expect(cards).to_have_count(4)
        expect(page.locator("#detail")).to_contain_text("row/column elision")
        search.fill("a query that matches no symbols")
        expect(cards).to_have_count(0)
        expect(page.locator("#group-filter")).to_have_value("Matrix ellipses")
        expect(page.locator("#results")).to_contain_text("No candidates match")

        page.get_by_role("button", name="Reset filters").click()
        page.locator("#group-by").select_option("block")
        page.locator("#group-filter").select_option("Mathematical Operators")
        expect(cards).to_have_count(256)
        page.locator("#symbol-8745").click()
        page.evaluate("window.scrollTo(0, 0)")
        expect(page.locator("#toast")).to_be_empty(timeout=5000)
        page.screenshot(path=ROOT / "target" / "inventory-desktop.png")
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        )

        page.set_viewport_size({"width": 390, "height": 844})
        search.fill("U+2229")
        expect(cards).to_have_count(1)
        cards.click()
        expect(page.locator(".detail-title")).to_be_in_viewport()
        page.screenshot(path=ROOT / "target" / "inventory-mobile.png")
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        )
        assert not errors, errors
        assert not [url for url in network if url.startswith(("http:", "https:"))], (
            network
        )
        print(
            "Offline file:// checks passed: groups, search, filters, exact clipboard text, variants, combining marks, invisible characters, and mobile layout."
        )
        print(
            "Screenshots: target/inventory-desktop.png and target/inventory-mobile.png"
        )
        browser.close()


if __name__ == "__main__":
    main()
