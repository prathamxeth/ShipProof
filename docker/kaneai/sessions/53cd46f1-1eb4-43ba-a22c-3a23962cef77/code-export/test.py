import os
import testmu
from testmu import expect, var, set_var
from playwright.async_api import Page

testmu.configure(
    build="e733e57d-58d9-4317-9d6c-bdfd1ba7bce6",
    name="Verify Store Homepage Loads",
    tc_id="TC-10",
    network=os.getenv("NETWORK", "false").lower() == "true",
    variables={"store_homepage_loaded": "true"},
    auto_heal_version="AH2",
    default_action_timeout_ms=60000,
    default_navigation_timeout_ms=60000,
    kane_run_v4=True,
)

@testmu.test
async def test(page: Page):
    async with testmu.step('Navigate to http://127.0.0.1:3005', instruction_id='3db038fc-b03b-4253-bcd9-94c54c0aed68'):
        await page.goto("http://127.0.0.1:3005")
    
    async with testmu.step('Checking whether the store homepage loaded'):
        set_var('store_homepage_loaded', await testmu.textual_analyzer(page, wrapped_js="(els) => {\n  const __m = {7: 0};\n  const el = (i) => els[__m[i]];\n  const __v = (!!el(7).textContent.trim());\n  return (typeof __v === 'boolean' ? String(__v) : __v);\n}", locators=['internal:role=heading[name="Featured Tech Gear"i]'], query='whether store homepage loaded is present (in the main catalog content)', expected_value='true', needs_unit_conversion=False, operator='equals', transforms=[], condition='store homepage loads'))
    
    async with testmu.step('Assertion check', instruction_id='20adc542-1faf-4fa9-ab4e-4ecffc3a571e'):
        await testmu.verify_assertion(page, 'Assertion check', {'operator': ['equals'], 'assertion_operands': [], 'left_operand': None, 'right_operand': None, 'operands': [], 'sub_results': [{'description': 'store homepage loads', 'passed': True, 'operator': 'equals', 'transforms': [], 'json_path': None, 'expected': 'true', 'extracted_value': '{{store_homepage_loaded}}', 'store_key': 'store_homepage_loaded', 'variable_refs': {'{{store_homepage_loaded}}': 'true'}}], 'sub_checks': [{'description': 'store homepage loads', 'store_key': 'store_homepage_loaded', 'expected_value': 'true', 'extracted_value': '{{store_homepage_loaded}}', 'operator': 'equals', 'transforms': []}], 'composite_operator': 'and', 'claim': 'store homepage loads'})


if __name__ == "__main__":
    testmu.run(test)