import os
import testmu
from testmu import expect, var, set_var
from playwright.async_api import Page

testmu.configure(
    build="ec068e14-107f-4299-813e-8b0ea242d51e",
    name="Verify Secure Checkout Process",
    tc_id="TC-8",
    network=os.getenv("NETWORK", "false").lower() == "true",
    auto_heal_version="AH2",
    default_action_timeout_ms=60000,
    default_navigation_timeout_ms=60000,
    kane_run_v4=True,
)

@testmu.test
async def test(page: Page):
    async with testmu.step('Navigate to http://127.0.0.1:3005/product/1', instruction_id='45d9c0ff-729c-4081-bd44-b047000e78b8'):
        await page.goto("http://127.0.0.1:3005/product/1")
    
    async with testmu.step('Clicking Add to Cart', instruction_id='f330c0f8-52ed-4d9a-b514-8f4dbcfefa7b'):
        _loc_1 = page.locator("internal:role=button[name=\"Add to Cart\"i]")
        
        await _loc_1.click()


if __name__ == "__main__":
    testmu.run(test)