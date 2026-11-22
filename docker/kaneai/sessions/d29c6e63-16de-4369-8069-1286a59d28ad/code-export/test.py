import os
import testmu
from testmu import expect, var, set_var
from playwright.async_api import Page

testmu.configure(
    build="d7446201-d8a1-46fc-aa04-bf13152b47ba",
    name="View Catalog",
    tc_id="TC-37",
    network=os.getenv("NETWORK", "false").lower() == "true",
    auto_heal_version="AH2",
    default_action_timeout_ms=60000,
    default_navigation_timeout_ms=60000,
    kane_run_v4=True,
)

@testmu.test
async def test(page: Page):
    async with testmu.step('Navigate to http://127.0.0.1:3005', instruction_id='5ff417b8-1154-4cdc-a347-021529e4424d'):
        await page.goto("http://127.0.0.1:3005")


if __name__ == "__main__":
    testmu.run(test)