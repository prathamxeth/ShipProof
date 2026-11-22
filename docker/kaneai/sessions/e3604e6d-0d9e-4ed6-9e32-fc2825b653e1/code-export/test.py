import os
import testmu
from testmu import expect, var, set_var
from playwright.async_api import Page

testmu.configure(
    build="6c85f67e-3255-4146-b336-b6e45f99a952",
    name="Verify Secure Checkout Display",
    tc_id="TC-9",
    network=os.getenv("NETWORK", "false").lower() == "true",
    variables={"secure_checkout_displayed": "true"},
    auto_heal_version="AH2",
    default_action_timeout_ms=60000,
    default_navigation_timeout_ms=60000,
    kane_run_v4=True,
)

@testmu.test
async def test(page: Page):
    async with testmu.step('Navigate to http://127.0.0.1:3005/product/1', instruction_id='f021ea24-f2f3-403d-beb6-d7d83d741ade'):
        await page.goto("http://127.0.0.1:3005/product/1")
    
    async with testmu.step('Clicking Add to Cart', instruction_id='8d3de9b9-90f4-4dc9-be94-9f09f1cabf3e'):
        _loc_1 = page.locator("internal:role=button[name=\"Add to Cart\"i]")
        
        await _loc_1.click()
    
    async with testmu.step('Clicking Proceed to Checkout in the cart summary panel', instruction_id='b172a7bc-e972-4d6d-b66f-79bf8c2643ad'):
        _loc_2 = page.locator("internal:role=link[name=\"Proceed to Checkout\"i]")
        
        await _loc_2.click()
    _condition_met = False
    _until_retries = 0
    while _until_retries < 10:
        print(f"[until-loop] iteration {_until_retries + 1}/10")
        async with testmu.step('Waiting for Secure Checkout heading to be visible', instruction_id='395ebc5d-14c7-4a31-a43e-0ae44ef83c02'):
            await page.wait_for_timeout(1000)
        await page.wait_for_timeout(500)
        if await testmu.check_until_condition(page, 'the heading "Secure Checkout" is visible'):
            _condition_met = True
            break
        _until_retries += 1
    set_var("__result__", {"condition_met": _condition_met, "retries": _until_retries + 1})
    
    async with testmu.step('Checking whether Secure Checkout is displayed'):
        set_var('secure_checkout_displayed', await testmu.textual_analyzer(page, wrapped_js="(els) => {\n  const __m = {8: 0};\n  const el = (i) => els[__m[i]];\n  const __v = (el(8).textContent.trim() === 'Secure Checkout' && el(8).getClientRects().length > 0);\n  return (typeof __v === 'boolean' ? String(__v) : __v);\n}", locators=['internal:role=heading[name="Secure Checkout"i]'], query="whether 'Secure Checkout' is present (as the main checkout heading)", expected_value='true', needs_unit_conversion=False, operator='equals', transforms=[], condition="'Secure Checkout' is displayed"))
    
    async with testmu.step('Assertion check', instruction_id='435707a8-6751-4e7c-a34b-272f919fe76c'):
        await testmu.verify_assertion(page, 'Assertion check', {'operator': ['equals'], 'assertion_operands': [], 'left_operand': None, 'right_operand': None, 'operands': [], 'sub_results': [{'description': "'Secure Checkout' is displayed", 'passed': True, 'operator': 'equals', 'transforms': [], 'json_path': None, 'expected': 'true', 'extracted_value': '{{secure_checkout_displayed}}', 'store_key': 'secure_checkout_displayed', 'variable_refs': {'{{secure_checkout_displayed}}': 'true'}}], 'sub_checks': [{'description': "'Secure Checkout' is displayed", 'store_key': 'secure_checkout_displayed', 'expected_value': 'true', 'extracted_value': '{{secure_checkout_displayed}}', 'operator': 'equals', 'transforms': []}], 'composite_operator': 'and', 'claim': "'Secure Checkout' is displayed"})


if __name__ == "__main__":
    testmu.run(test)