import os
import testmu
from testmu import expect, var, set_var
from playwright.async_api import Page

testmu.configure(
    build="743adc18-4de3-4f2b-b1f0-ce4f2604a7b9",
    name="Verify ShipProof Navigation and Content",
    tc_id="TC-12",
    network=os.getenv("NETWORK", "false").lower() == "true",
    variables={"shipproof_heading_check": "true", "verification_runs_listed": "true"},
    auto_heal_version="AH2",
    default_action_timeout_ms=60000,
    default_navigation_timeout_ms=60000,
    kane_run_v4=True,
)

@testmu.test
async def test(page: Page):
    async with testmu.step('Navigate to http://localhost:3000', instruction_id='b8b486c0-c42b-484c-b314-73f22d1d14c4'):
        await page.goto("http://localhost:3000")
    
    async with testmu.step('Checking whether the ShipProof heading is present'):
        set_var('shipproof_heading_check', await testmu.textual_analyzer(page, wrapped_js="(els) => {\n  const __m = {4: 0};\n  const el = (i) => els[__m[i]];\n  const __v = (el(4).innerText.includes('ShipProof'));\n  return (typeof __v === 'boolean' ? String(__v) : __v);\n}", locators=['internal:role=link[name="ShipProof Verification &"i]'], query='whether heading ShipProof is present (in the homepage hero section)', expected_value='true', needs_unit_conversion=False, operator='equals', transforms=[], condition='The ShipProof homepage has the heading ShipProof.'))
    
    async with testmu.step('Assertion check', instruction_id='3da1099f-eb58-4918-a0d8-ae867bb25820'):
        await testmu.verify_assertion(page, 'Assertion check', {'operator': ['equals'], 'assertion_operands': [], 'left_operand': None, 'right_operand': None, 'operands': [], 'sub_results': [{'description': 'The ShipProof homepage has the heading ShipProof.', 'passed': True, 'operator': 'equals', 'transforms': [], 'json_path': None, 'expected': 'true', 'extracted_value': '{{shipproof_heading_check}}', 'store_key': 'shipproof_heading_check', 'variable_refs': {'{{shipproof_heading_check}}': 'true'}}], 'sub_checks': [{'description': 'The ShipProof homepage has the heading ShipProof.', 'store_key': 'shipproof_heading_check', 'expected_value': 'true', 'extracted_value': '{{shipproof_heading_check}}', 'operator': 'equals', 'transforms': []}], 'composite_operator': 'and', 'claim': 'ShipProof homepage loads with heading ShipProof'})
    
    async with testmu.step('Scroll into view: PRIMARY: Click on Verification Runs; role=link; text="Verification Runs" | HINTS: container=left navigation', instruction_id='842c44d1-ae4f-4279-99cc-fb2b850f68bc'):
        element_0 = page.locator("internal:role=link[name=\"Verification Runs\"i]")
        await element_0.evaluate("el => el.scrollIntoView({block: 'center'})")
    
    async with testmu.step('Clicking on Verification Runs in the left navigation menu', instruction_id='18f94540-2a60-42e2-a1ea-8e446edde7ef'):
        _loc_1 = page.locator("internal:role=link[name=\"Verification Runs\"i]")
        
        await _loc_1.click()
    _condition_met = False
    _until_retries = 0
    while _until_retries < 10:
        print(f"[until-loop] iteration {_until_retries + 1}/10")
        async with testmu.step('Waiting for Verification Runs heading to be visible', instruction_id='6e9d2fe3-22c0-480b-b61e-e9744a8be3ca'):
            await page.wait_for_timeout(500)
        await page.wait_for_timeout(500)
        if await testmu.check_until_condition(page, "the heading 'Verification Runs' is visible"):
            _condition_met = True
            break
        _until_retries += 1
    set_var("__result__", {"condition_met": _condition_met, "retries": _until_retries + 1})
    
    async with testmu.step('Checking whether Verification runs are listed'):
        set_var('verification_runs_listed', await testmu.textual_analyzer(page, wrapped_js='(els) => {\n  const __m = {44: 0};\n  const el = (i) => els[__m[i]];\n  const __v = (el(44).matches(\'a[href*="/runs/"]\') && el(44).textContent.includes(\'Verification Run\'));\n  return (typeof __v === \'boolean\' ? String(__v) : __v);\n}', locators=['internal:role=link[name="Passed#aa2534d2 API Audit"i]'], query='whether Verification runs is present (in the verification runs list)', expected_value='true', needs_unit_conversion=False, operator='equals', transforms=[], condition='Verification runs are listed.'))
    
    async with testmu.step('Assertion check', instruction_id='bb9a86ae-58d9-436a-b05e-ed66bffcea88'):
        await testmu.verify_assertion(page, 'Assertion check', {'operator': ['equals'], 'assertion_operands': [], 'left_operand': None, 'right_operand': None, 'operands': [], 'sub_results': [{'description': 'Verification runs are listed.', 'passed': True, 'operator': 'equals', 'transforms': [], 'json_path': None, 'expected': 'true', 'extracted_value': '{{verification_runs_listed}}', 'store_key': 'verification_runs_listed', 'variable_refs': {'{{verification_runs_listed}}': 'true'}}], 'sub_checks': [{'description': 'Verification runs are listed.', 'store_key': 'verification_runs_listed', 'expected_value': 'true', 'extracted_value': '{{verification_runs_listed}}', 'operator': 'equals', 'transforms': []}], 'composite_operator': 'and', 'claim': 'runs are listed'})
    
    async with testmu.step('Scroll into view: PRIMARY: Click on Repair Studio; role=link; text="Repair Studio" | HINTS: container=left navigation', instruction_id='49dca0e0-0ff8-44e3-aeab-076a842ed221'):
        element_1 = page.locator("internal:role=link[name=\"Repair Studio\"i]")
        await element_1.evaluate("el => el.scrollIntoView({block: 'center'})")
    
    async with testmu.step('Clicking Repair Studio in the left navigation', instruction_id='ff8f44ec-6ec5-4300-8664-392263d23a50'):
        _loc_2 = page.locator("internal:role=link[name=\"Repair Studio\"i]")
        
        await _loc_2.click()
    
    async with testmu.step('Scroll into view: PRIMARY: Click on Projects; role=link; text="Projects" | HINTS: container=left navigation', instruction_id='729f69ca-f37d-44cf-a4ba-3c973e1932ae'):
        element_2 = page.locator("internal:role=link[name=\"Projects\"i]")
        await element_2.evaluate("el => el.scrollIntoView({block: 'center'})")
    
    async with testmu.step('Clicking Projects in the left navigation', instruction_id='c3a63ade-4508-4c5a-8c78-cd2012a0c8c2'):
        _loc_3 = page.locator("internal:role=link[name=\"Projects\"i]")
        
        await _loc_3.click()
    
    async with testmu.step('Clicking Settings in the left navigation', instruction_id='1b46e8ad-a6c2-4ef7-acfa-4a6cab1e4896'):
        _loc_4 = page.locator("internal:role=link[name=\"Settings\"i]")
        
        await _loc_4.click()


if __name__ == "__main__":
    testmu.run(test)