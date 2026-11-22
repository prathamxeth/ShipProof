import os
import testmu
from testmu import expect, var, set_var
from playwright.async_api import Page

testmu.configure(
    build="accbda5d-d81e-4354-9829-640239838d9a",
    name="Verify Secure Checkout Display",
    tc_id="TC-4",
    network=os.getenv("NETWORK", "false").lower() == "true",
    auto_heal_version="AH2",
    default_action_timeout_ms=60000,
    default_navigation_timeout_ms=60000,
    kane_run_v4=True,
)

@testmu.test
async def test(page: Page):
    async with testmu.step('Navigate to http://127.0.0.1:3005/product/1', instruction_id='dadc22ea-c39a-467b-9451-b712bdedc53f'):
        await page.goto("http://127.0.0.1:3005/product/1")
    
    async with testmu.step('Clicking Add to Cart', instruction_id='1d6be5dc-6f68-4369-af27-7f2cbee334b9'):
        _loc_1 = page.locator("internal:role=button[name=\"Add to Cart\"i]")
        
        await _loc_1.click()
    
    async with testmu.step('Clicking Update button for cart item quantity', instruction_id='84a0bcdf-26b5-412b-8932-e4d850acb15b'):
        _loc_2 = page.locator("internal:role=button[name=\"Update\"i]")
        
        await _loc_2.click()


if __name__ == "__main__":
    testmu.run(test)