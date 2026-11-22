import os
import testmu
from testmu import expect, var, set_var
from playwright.async_api import Page

testmu.configure(
    build="29235bc5-ca27-410a-884b-c5c0f0d7562d",
    name="Verify Page Load",
    tc_id="TC-19",
    network=os.getenv("NETWORK", "false").lower() == "true",
    variables={"page_loaded_check": "true"},
    auto_heal_version="AH2",
    default_action_timeout_ms=60000,
    default_navigation_timeout_ms=60000,
    kane_run_v4=True,
)

@testmu.test
async def test(page: Page):
    async with testmu.step('Navigate to https://example.com', instruction_id='2d709896-30f8-488b-b223-18217baf8eb1'):
        await page.goto("https://example.com")
    
    async with testmu.step('whether page loaded is present (in the browser viewport)', instruction_id='5fccdc7a-ae6f-41c8-8bf3-e359316fa960'):
        set_var('page_loaded_check', await testmu.vision_query(page, "whether page loaded is present (in the browser viewport)", ""))
    
    async with testmu.step('Assertion check', instruction_id='a80ba2e8-e379-4126-8218-4a2cf5539636'):
        await testmu.verify_assertion(page, 'Assertion check', {'operator': ['equals'], 'assertion_operands': [], 'left_operand': None, 'right_operand': None, 'operands': [], 'sub_results': [{'description': 'page loaded', 'passed': True, 'operator': 'equals', 'transforms': [], 'json_path': None, 'expected': 'true', 'extracted_value': '{{page_loaded_check}}', 'store_key': 'page_loaded_check', 'variable_refs': {'{{page_loaded_check}}': 'true'}}], 'sub_checks': [{'description': 'page loaded', 'store_key': 'page_loaded_check', 'expected_value': 'true', 'extracted_value': '{{page_loaded_check}}', 'operator': 'equals', 'transforms': []}], 'composite_operator': 'and', 'claim': 'page loaded'})


if __name__ == "__main__":
    testmu.run(test)