import os
import testmu
from testmu import expect, var, set_var
from playwright.async_api import Page

testmu.configure(
    build="89854216-38a0-42af-8715-709e15dd09ef",
    name="Verify Secure Checkout Process",
    tc_id="TC-5",
    network=os.getenv("NETWORK", "false").lower() == "true",
    auto_heal_version="AH2",
    default_action_timeout_ms=60000,
    default_navigation_timeout_ms=60000,
    kane_run_v4=True,
)

@testmu.test
async def test(page: Page):
    async with testmu.step('Navigate to http://127.0.0.1:3005/product/1', instruction_id='628865e7-0422-4a9c-a125-e4f2f7794ce3'):
        await page.goto("http://127.0.0.1:3005/product/1")
    
    async with testmu.step('Clicking Add to Cart', instruction_id='fc2d2590-2fb4-456d-bc09-17ab3598ceb7'):
        _loc_1 = page.locator("internal:role=button[name=\"Add to Cart\"i]")
        
        await _loc_1.click()


if __name__ == "__main__":
    testmu.run(test)