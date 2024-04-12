#!/usr/bin/env python3
#
# To debug: PWDEBUG=1 pytest browser_tests.py

import sys

import anyio
import portpicker
import pytest
from flyweb.examples.misc import __main__
from playwright import async_api


@pytest.mark.anyio
async def test_browser_tests():
    async with anyio.create_task_group() as tg:
        port = portpicker.pick_unused_port()
        tg.start_soon(__main__.main, port)
        async with async_api.async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()

            # Append all console messages to a list.
            console_messages = []
            page.on("console", lambda msg: console_messages.append(msg))

            await page.goto(f"http://localhost:{port}")
            await async_api.expect(
                page.get_by_role(
                    "heading", name="Demo of different elements and events"
                )
            ).to_be_visible()

            await async_api.expect(
                page.get_by_text("checkbox1 checked = False")
            ).to_be_visible()

            await async_api.expect(
                page.get_by_text("checkbox2 checked = True")
            ).to_be_visible()

            await page.click("#checkbox1")

            await async_api.expect(
                page.get_by_text("checkbox1 checked = True")
            ).to_be_visible()

            await page.click("#checkbox2")

            await async_api.expect(
                page.get_by_text("checkbox2 checked = False")
            ).to_be_visible()

            await async_api.expect(page.locator("#text_input")).to_have_value("foo")
            await async_api.expect(page.get_by_text("value = foo")).to_be_visible()

            await page.locator("#text_input").press("End")
            await page.locator("#text_input").press("Backspace")
            await page.locator("#text_input").press("u")
            await page.locator("#text_input").press("n")
            await page.locator("#text_input").press("d")

            # We shouldn't have updated the "value = [..]" text yet.
            await async_api.expect(page.get_by_text("value = foo")).to_be_visible()

            # Now focus somewhere else and it should get updated.
            await page.click("#checkbox1")
            await async_api.expect(page.get_by_text("value = found")).to_be_visible()

            # Test that we can handle individual_key_down_handlers.
            await page.locator("#text_input").press("Escape")
            await async_api.expect(page.locator("textarea")).to_contain_text(
                "text input custom key down"
            )
            await async_api.expect(page.locator("textarea")).to_contain_text(
                "'key': 'Escape'"
            )
            # This should have cleared out the text input.
            await async_api.expect(page.locator("#text_input")).to_have_value("")

            # Now type some stuff in again.
            await page.locator("#text_input").press("a")
            await page.locator("#text_input").press("b")
            await page.locator("#text_input").press("c")
            await async_api.expect(page.locator("#text_input")).to_have_value("abc")

            # And clear it again.
            await page.locator("#text_input").press("Escape")
            await async_api.expect(page.locator("#text_input")).to_have_value("")

            # Test that title starts out as "flyweb".
            title = await page.title()
            assert title == "flyweb"

            # Test that pressing Enter on the text replaces page title.
            await page.locator("#text_input").press("h")
            await page.locator("#text_input").press("i")
            await page.locator("#text_input").press("Enter")
            title = await page.title()
            assert title == "hi"

            # Test mouseover.
            await page.get_by_text("mouse over me").hover()
            await async_api.expect(page.locator("textarea")).to_contain_text(
                "span onmouseover"
            )

            # Test button onclick.
            await page.get_by_role("button").click()
            await async_api.expect(page.locator("textarea")).to_contain_text(
                "button onclick"
            )

            # Make sure we didn't forget any debug info in the console log.
            assert console_messages == []

            await page.pause()
            tg.cancel_scope.cancel()

        await browser.close()


if __name__ == "__main__":
    pytest.main(sys.argv)
