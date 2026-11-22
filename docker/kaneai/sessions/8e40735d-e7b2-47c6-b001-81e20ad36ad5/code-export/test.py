import os
import testmu
from testmu import expect, var, set_var
from playwright.async_api import Page

testmu.configure(
    build="6e970b52-5493-44ec-a09c-f68908b2c420",
    name="Verify Secure Checkout Display",
    tc_id="TC-7",
    network=os.getenv("NETWORK", "false").lower() == "true",
    variables={"secure_checkout_displayed": "true"},
    auto_heal_version="AH2",
    default_action_timeout_ms=60000,
    default_navigation_timeout_ms=60000,
    kane_run_v4=True,
)

@testmu.test
async def test(page: Page):
    async with testmu.step('Navigate to http://127.0.0.1:3005/product/1', instruction_id='328cadde-45bc-4635-a08b-db9a7219e3b7'):
        await page.goto("http://127.0.0.1:3005/product/1")
    
    async with testmu.step('Clicking Add to Cart for the Wireless Noise-Cancelling Headphones', instruction_id='d1eed618-8d29-4aee-bf83-0b8ca8461611'):
        _loc_1 = page.locator("internal:role=button[name=\"Add to Cart\"i]")
        
        await _loc_1.click()
    
    async with testmu.step('Clicking Proceed to Checkout in the cart totals section', instruction_id='ccf12062-58c7-483c-93dd-861ff89e9eec'):
        _loc_2 = page.locator("internal:role=link[name=\"Proceed to Checkout\"i]")
        
        await _loc_2.click()
    _condition_met = False
    _until_retries = 0
    while _until_retries < 10:
        print(f"[until-loop] iteration {_until_retries + 1}/10")
        async with testmu.step('Waiting for Secure Checkout heading to be visible', instruction_id='2cfb127a-9383-476f-a4f6-854c1e0830b0'):
            await page.wait_for_timeout(500)
        await page.wait_for_timeout(500)
        if await testmu.check_until_condition(page, "the heading 'Secure Checkout' is visible"):
            _condition_met = True
            break
        _until_retries += 1
    set_var("__result__", {"condition_met": _condition_met, "retries": _until_retries + 1})
    
    async with testmu.step('Checking whether the Secure Checkout heading is present'):
        set_var('secure_checkout_displayed', await testmu.textual_analyzer(page, wrapped_js="(els) => {\n  const __m = {8: 0};\n  const el = (i) => els[__m[i]];\n  const __v = (el(8).textContent.trim() === 'Secure Checkout');\n  return (typeof __v === 'boolean' ? String(__v) : __v);\n}", locators=['internal:role=heading[name="Secure Checkout"i]'], query="whether 'Secure Checkout' is present (at the top of the checkout page)", expected_value='true', needs_unit_conversion=False, operator='equals', transforms=[], condition="'Secure Checkout' is displayed"))
    
    async with testmu.step('Assertion check', instruction_id='7db908f3-0955-4ee2-8436-e316238285e7'):
        await testmu.verify_assertion(page, 'Assertion check', {'operator': ['equals'], 'assertion_operands': [], 'left_operand': None, 'right_operand': None, 'operands': [], 'sub_results': [{'description': "'Secure Checkout' is displayed", 'passed': True, 'operator': 'equals', 'transforms': [], 'json_path': None, 'expected': 'true', 'extracted_value': '{{secure_checkout_displayed}}', 'store_key': 'secure_checkout_displayed', 'variable_refs': {'{{secure_checkout_displayed}}': 'true'}}], 'sub_checks': [{'description': "'Secure Checkout' is displayed", 'store_key': 'secure_checkout_displayed', 'expected_value': 'true', 'extracted_value': '{{secure_checkout_displayed}}', 'operator': 'equals', 'transforms': []}], 'composite_operator': 'and', 'claim': "'Secure Checkout' is displayed"})


if __name__ == "__main__":
    testmu.run(test)