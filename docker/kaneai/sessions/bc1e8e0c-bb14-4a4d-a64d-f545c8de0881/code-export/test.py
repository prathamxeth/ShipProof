import os
import testmu
from testmu import expect, var, set_var
from playwright.async_api import Page

testmu.configure(
    build="8550911e-d535-42d0-9f5e-b97e9f5bce8f",
    name="Verify Page Title",
    tc_id="TC-3",
    network=os.getenv("NETWORK", "false").lower() == "true",
    variables={"page_title_check": "ShipProof Tech Store \u2014 Catalog"},
    auto_heal_version="AH2",
    default_action_timeout_ms=60000,
    default_navigation_timeout_ms=60000,
    kane_run_v4=True,
)

@testmu.test
async def test(page: Page):
    async with testmu.step('Navigate to http://127.0.0.1:3005', instruction_id='65644f2e-8ea6-49dc-b609-3bfabd9d525e'):
        await page.goto("http://127.0.0.1:3005")
    
    async with testmu.step('Reading the current page title', instruction_id='20958c4c-4384-4dfc-8b97-190db46781f2'):
        set_var('page_title_check', await page.title())
    
    async with testmu.step('Assertion check', instruction_id='126a7d57-2f64-4db8-8c9d-1740cdb53421'):
        await testmu.verify_assertion(page, 'Assertion check', {'operator': ['equals'], 'assertion_operands': [], 'left_operand': None, 'right_operand': None, 'operands': [], 'sub_results': [{'description': "the page title contains 'ShipProof Tech Store'", 'passed': True, 'operator': 'contains', 'transforms': [], 'json_path': None, 'expected': 'ShipProof Tech Store', 'extracted_value': '{{page_title_check}}', 'store_key': 'page_title_check', 'variable_refs': {'{{page_title_check}}': 'ShipProof Tech Store — Catalog'}}], 'sub_checks': [{'description': "the page title contains 'ShipProof Tech Store'", 'store_key': 'page_title_check', 'expected_value': 'ShipProof Tech Store', 'extracted_value': '{{page_title_check}}', 'operator': 'contains', 'transforms': []}], 'composite_operator': 'and', 'claim': "the page title contains 'ShipProof Tech Store'"})


if __name__ == "__main__":
    testmu.run(test)