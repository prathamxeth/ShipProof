import os
import testmu
from testmu import expect, var, set_var
from playwright.async_api import Page

testmu.configure(
    build="4a394173-9be3-44d3-9472-d49b49d6988d",
    name="Verify Secure Checkout Process",
    tc_id="TC-13",
    network=os.getenv("NETWORK", "false").lower() == "true",
    auto_heal_version="AH2",
    default_action_timeout_ms=60000,
    default_navigation_timeout_ms=60000,
    kane_run_v4=True,
)

@testmu.test
async def test(page: Page):
    async with testmu.step('Navigate to http://127.0.0.1:3005/product/1', instruction_id='792c92f9-fe65-49b2-8501-243ee2b033c9'):
        await page.goto("http://127.0.0.1:3005/product/1")
    
    async with testmu.step('Clicking Add to Cart button', instruction_id='0b34c1dd-f846-4cef-99bb-fb77c47240b2'):
        _loc_1 = page.locator("internal:role=button[name=\"Add to Cart\"i]")
        
        await _loc_1.click()


if __name__ == "__main__":
    testmu.run(test)