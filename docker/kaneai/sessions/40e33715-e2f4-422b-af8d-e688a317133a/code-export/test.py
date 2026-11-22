import os
import testmu
from testmu import expect, var, set_var
from playwright.async_api import Page

testmu.configure(
    build="3c1e104a-432d-4665-bf4f-23e1448fb0e9",
    name="Verify Secure Checkout Display",
    tc_id="TC-6",
    network=os.getenv("NETWORK", "false").lower() == "true",
    variables={"secure_checkout_displayed": "true"},
    auto_heal_version="AH2",
    default_action_timeout_ms=60000,
    default_navigation_timeout_ms=60000,
    kane_run_v4=True,
)

@testmu.test
async def test(page: Page):
    async with testmu.step('Navigate to http://127.0.0.1:3005/product/1', instruction_id='1297e440-e7ef-48be-90da-ff25f1c6fce4'):
        await page.goto("http://127.0.0.1:3005/product/1")
    
    async with testmu.step('Clicking Add to Cart', instruction_id='e7e65d21-0722-4c15-b1dc-dad11aa83329'):
        _loc_1 = page.locator("internal:role=button[name=\"Add to Cart\"i]")
        
        await _loc_1.click()
    
    async with testmu.step('Clicking Proceed to Checkout in the cart', instruction_id='b9c80aa9-aa31-4793-8af7-78c9d87f688f'):
        _loc_2 = page.locator("internal:role=link[name=\"Proceed to Checkout\"i]")
        
        await _loc_2.click()
    _condition_met = False
    _until_retries = 0
    while _until_retries < 10:
        print(f"[until-loop] iteration {_until_retries + 1}/10")
        async with testmu.step('Waiting for the Secure Checkout page to load', instruction_id='5632778a-a4a8-4129-b448-66c068a3199d'):
            await page.wait_for_timeout(500)
        await page.wait_for_timeout(500)
        if await testmu.check_until_condition(page, "the heading 'Secure Checkout' is visible"):
            _condition_met = True
            break
        _until_retries += 1
    set_var("__result__", {"condition_met": _condition_met, "retries": _until_retries + 1})
    
    async with testmu.step('Checking whether Secure Checkout is displayed'):
        set_var('secure_checkout_displayed', await testmu.textual_analyzer(page, wrapped_js="(els) => {\n  const __m = {8: 0};\n  const el = (i) => els[__m[i]];\n  const __v = (el(8).textContent.trim() === 'Secure Checkout' && !!(el(8).offsetWidth || el(8).offsetHeight || el(8).getClientRects().length));\n  return (typeof __v === 'boolean' ? String(__v) : __v);\n}", locators=['internal:role=heading[name="Secure Checkout"i]'], query="whether 'Secure Checkout' is present (as the main checkout heading)", expected_value='true', needs_unit_conversion=False, operator='equals', transforms=[], condition="'Secure Checkout' is displayed."))
    
    async with testmu.step('Assertion check', instruction_id='9b858b0e-e29d-49b8-802b-330ed6116991'):
        await testmu.verify_assertion(page, 'Assertion check', {'operator': ['equals'], 'assertion_operands': [], 'left_operand': None, 'right_operand': None, 'operands': [], 'sub_results': [{'description': "'Secure Checkout' is displayed.", 'passed': True, 'operator': 'equals', 'transforms': [], 'json_path': None, 'expected': 'true', 'extracted_value': '{{secure_checkout_displayed}}', 'store_key': 'secure_checkout_displayed', 'variable_refs': {'{{secure_checkout_displayed}}': 'true'}}], 'sub_checks': [{'description': "'Secure Checkout' is displayed.", 'store_key': 'secure_checkout_displayed', 'expected_value': 'true', 'extracted_value': '{{secure_checkout_displayed}}', 'operator': 'equals', 'transforms': []}], 'composite_operator': 'and', 'claim': "'Secure Checkout' is displayed."})


if __name__ == "__main__":
    testmu.run(test)