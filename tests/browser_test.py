#!/usr/bin/env python3

import sys

import anyio
from playwright import async_api
import pytest

from flyweb.examples.todo import __main__


@pytest.mark.anyio
async def test_todo_example():
    async with async_api.async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        async with anyio.create_task_group() as tg:
            # TODO: auto-pick a port.
            port = 8001
            tg.start_soon(__main__.main, port)
            await page.goto(f"http://localhost:{port}")
            await async_api.expect(
                page.get_by_role("heading", name="To Do")
            ).to_be_visible()

            write_code_text = page.get_by_text("write code")
            write_code_checkbox = page.get_by_role("checkbox", name="write code")
            write_more_code_text = page.get_by_text("write more code")
            write_more_code_checkbox = page.get_by_role(
                "checkbox", name="write more code"
            )
            await async_api.expect(write_code_text).to_be_visible()
            await async_api.expect(write_code_checkbox).to_be_visible()
            await async_api.expect(write_code_checkbox).to_be_checked()
            await async_api.expect(write_more_code_text).to_be_visible()
            await async_api.expect(write_more_code_checkbox).to_be_visible()
            await async_api.expect(write_more_code_checkbox).not_to_be_checked()

            await write_code_checkbox.click()
            await async_api.expect(write_code_checkbox).not_to_be_checked()
            await write_code_text.click()
            await async_api.expect(write_code_checkbox).to_be_checked()

            # Double click the label to edit it, then click away.
            await page.get_by_text("write code").dblclick()
            await async_api.expect(
                page.get_by_role("listitem").get_by_role("textbox")
            ).to_be_editable()
            await page.keyboard.press("Control+A")
            # TODO: once we are not sending events for every keypress, this
            # delay can be reduced.
            await page.keyboard.type("procrastinate", delay=100)
            await page.locator("html").click()
            await async_api.expect(
                page.get_by_role("listitem").get_by_role("textbox")
            ).to_have_count(0)
            await async_api.expect(page.get_by_text("procrastinate")).to_be_visible()

            # Double click the label to edit it, then press enter.
            await page.get_by_text("procrastinate").dblclick()
            await async_api.expect(
                page.get_by_role("listitem").get_by_role("textbox")
            ).to_be_editable()
            await page.keyboard.press("Control+A")
            await page.keyboard.type("eat pizza", delay=100)
            # TODO: re-add when supported.
            # await page.keyboard.press("Enter")
            await page.locator("html").click()

            await async_api.expect(
                page.get_by_role("listitem").get_by_role("textbox")
            ).to_have_count(0)
            await async_api.expect(page.get_by_text("eat pizza")).to_be_visible()

            # Click "DELETE" button.
            await page.get_by_role("listitem").filter(has_text="eat pizza").get_by_role(
                "button", name="delete"
            ).click()

            await async_api.expect(page.get_by_text("eat pizza")).to_have_count(0)

            # Add a new item.
            await page.get_by_placeholder("do what?").click()
            await page.get_by_placeholder("do what?").fill("write tests")
            await page.get_by_role("button", name="add").click()

            await async_api.expect(page.get_by_text("write tests")).to_be_visible()

            await page.pause()
            tg.cancel_scope.cancel()

        await browser.close()


if __name__ == "__main__":
    pytest.main(sys.argv)
