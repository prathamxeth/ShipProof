import os
import testmu
from testmu import expect, var, set_var
from playwright.async_api import Page

testmu.configure(
    build="7a4e8d08-0905-4303-81bf-e6b0f7a44d88",
    name="Verify Secure Checkout Display",
    tc_id="TC-207",
    network=os.getenv("NETWORK", "false").lower() == "true",
    auto_heal_version="AH2",
    default_action_timeout_ms=60000,
    default_navigation_timeout_ms=60000,
    kane_run_v4=True,
)

@testmu.test
async def test(page: Page):
    async with testmu.step('Navigate to http://127.0.0.1:3005', instruction_id='acce9f81-824c-4ee9-a8e7-6684f2f912bd'):
        await page.goto("http://127.0.0.1:3005")
    
    async with testmu.step('Clicking Add to Cart', instruction_id='769a6985-445b-4a66-a67a-29d2d45c5d1b'):
        _loc_1 = page.locator("#add-to-cart-1")
        
        await _loc_1.click()


if __name__ == "__main__":
    testmu.run(test)