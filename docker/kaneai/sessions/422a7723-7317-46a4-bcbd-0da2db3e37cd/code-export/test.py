import os
import testmu
from testmu import expect, var, set_var
from playwright.async_api import Page

testmu.configure(
    build="392c5cb1-c752-476a-bf41-eb8efa401468",
    name="Verify Secure Checkout Display",
    tc_id="TC-14",
    network=os.getenv("NETWORK", "false").lower() == "true",
    variables={"secure_checkout_displayed": "true"},
    auto_heal_version="AH2",
    default_action_timeout_ms=60000,
    default_navigation_timeout_ms=60000,
    kane_run_v4=True,
)

@testmu.test
async def test(page: Page):
    async with testmu.step('Navigate to http://127.0.0.1:3005/product/1', instruction_id='dd0ff95c-024c-4314-8eaf-f53949e63aec'):
        await page.goto("http://127.0.0.1:3005/product/1")
    
    async with testmu.step('Clicking Add to Cart for Wireless Noise-Cancelling Headphones', instruction_id='77d1f176-6967-4200-9b27-2a84bca30fad'):
        _loc_1 = page.locator("internal:role=button[name=\"Add to Cart\"i]")
        
        await _loc_1.click()
    
    async with testmu.step('Clicking Proceed to Checkout in the cart', instruction_id='b51ca3c4-d038-4064-a96c-7143a2bf95ae'):
        _loc_2 = page.locator("internal:role=link[name=\"Proceed to Checkout\"i]")
        
        await _loc_2.click()
    _condition_met = False
    _until_retries = 0
    while _until_retries < 10:
        print(f"[until-loop] iteration {_until_retries + 1}/10")
        async with testmu.step('Waiting for the Secure Checkout heading to be visible', instruction_id='865df3c0-4529-4bb4-8b7e-7932cc10bc78'):
            await page.wait_for_timeout(500)
        await page.wait_for_timeout(500)
        if await testmu.check_until_condition(page, "the heading 'Secure Checkout' is visible"):
            _condition_met = True
            break
        _until_retries += 1
    set_var("__result__", {"condition_met": _condition_met, "retries": _until_retries + 1})
    
    async with testmu.step('Checking whether the Secure Checkout heading is present'):
        set_var('secure_checkout_displayed', await testmu.textual_analyzer(page, wrapped_js="(els) => {\n  const __m = {8: 0};\n  const el = (i) => els[__m[i]];\n  const __v = (el(8).textContent.trim() === 'Secure Checkout');\n  return (typeof __v === 'boolean' ? String(__v) : __v);\n}", locators=['internal:role=heading[name="Secure Checkout"i]'], query="whether 'Secure Checkout' is present (at the top of the checkout form)", expected_value='true', needs_unit_conversion=False, operator='equals', transforms=[], condition="'Secure Checkout' is displayed."))
    
    async with testmu.step('Assertion check', instruction_id='ef885916-4f17-49c4-8b27-38b3c78dc4d6'):
        await testmu.verify_assertion(page, 'Assertion check', {'operator': ['equals'], 'assertion_operands': [], 'left_operand': None, 'right_operand': None, 'operands': [], 'sub_results': [{'description': "'Secure Checkout' is displayed.", 'passed': True, 'operator': 'equals', 'transforms': [], 'json_path': None, 'expected': 'true', 'extracted_value': '{{secure_checkout_displayed}}', 'store_key': 'secure_checkout_displayed', 'variable_refs': {'{{secure_checkout_displayed}}': 'true'}}], 'sub_checks': [{'description': "'Secure Checkout' is displayed.", 'store_key': 'secure_checkout_displayed', 'expected_value': 'true', 'extracted_value': '{{secure_checkout_displayed}}', 'operator': 'equals', 'transforms': []}], 'composite_operator': 'and', 'claim': "'Secure Checkout' is displayed."})


if __name__ == "__main__":
    testmu.run(test)