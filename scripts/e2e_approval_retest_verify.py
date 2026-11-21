import asyncio
import time
import httpx
import sys

BASE_URL = "http://localhost:3000"

async def main():
    print("=" * 60)
    print("SHIPPROOF E2E CONNECTIVITY & REPAIR VERIFICATION")
    print("=" * 60)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=120.0, trust_env=False) as client:
        # 1. Health check
        print("\n[1/7] Checking frontend and backend health...")
        r = await client.get("/api/health")
        assert r.status_code == 200, f"Health check failed: {r.status_code}"
        health = r.json()
        print(f"✓ Health: status={health.get('status')}, kane_cli={health.get('kane_cli_installed')}, mode={health.get('execution_mode')}")

        # 2. Authenticate
        print("\n[2/7] Authenticating operator session...")
        r = await client.post("/api/auth/login", json={"key": "demo"})
        assert r.status_code == 200, f"Login failed: {r.status_code}"
        print("✓ Session authenticated.")

        # 3. Inject Defect
        print("\n[3/7] Injecting checkout defect through frontend proxy...")
        r = await client.post("/api/guard/defect", json={"enabled": True})
        assert r.status_code == 200, f"Defect toggle failed: {r.status_code}"
        defect_info = r.json()
        print(f"✓ Defect status: {defect_info}")

        # 4. Trigger Real Shopper Probe
        print("\n[4/7] Triggering real Kane CLI Secret Shopper probe...")
        r = await client.post("/api/guard/probe")
        assert r.status_code == 200, f"Probe trigger failed: {r.status_code}"
        probe_data = r.json()
        run_id = probe_data["run_id"]
        print(f"✓ Probe launched with Run ID: {run_id}")

        # Wait for probe to complete (expecting failed status due to defect)
        print("  Waiting for probe execution in Chromium...")
        final_run_status = None
        for _ in range(30):
            await asyncio.sleep(4)
            r = await client.get(f"/api/runs/{run_id}")
            if r.status_code == 200:
                run_state = r.json()
                status = run_state.get("status")
                print(f"  ... Run {run_id[:8]} status: {status}")
                if status in ("failed", "passed", "error"):
                    final_run_status = status
                    break

        assert final_run_status == "failed", f"Expected probe to fail due to defect, got: {final_run_status}"
        print("✓ Defect successfully detected by Kane CLI shopper simulation!")

        # 5. Wait for Repair Session to reach AWAITING_APPROVAL
        print("\n[5/7] Waiting for AI repair formulation (AWAITING_APPROVAL)...")
        target_repair = None
        for _ in range(25):
            await asyncio.sleep(2)
            r = await client.get("/api/repairs")
            if r.status_code == 200:
                repairs = r.json()
                for rep in repairs:
                    if rep.get("run_id") == run_id and rep.get("status") == "AWAITING_APPROVAL":
                        target_repair = rep
                        break
            if target_repair:
                break

        assert target_repair is not None, "Repair did not reach AWAITING_APPROVAL"
        repair_id = target_repair["id"]
        print(f"✓ Repair session active: {repair_id}")
        print(f"  Diagnosis: {target_repair.get('diagnosis')[:80]}...")
        print(f"  Patch available: {bool(target_repair.get('patch_diff'))}")

        # 6. Approve Repair
        print("\n[6/7] Authorizing human approval and applying patch...")
        r = await client.post(
            f"/api/repairs/{repair_id}/approve",
            json={"decision": "APPROVE", "rationale": "Verified by ShipProof test suite"}
        )
        assert r.status_code == 200, f"Approve failed: {r.status_code} - {r.text}"
        approve_resp = r.json()
        print(f"✓ Approval accepted: status={approve_resp.get('status')}, approver={approve_resp.get('approved_by')}")

        # 7. Monitor Retest and Confirm VERIFIED
        print("\n[7/7] Monitoring Kane CLI retest in Chromium...")
        final_repair_status = None
        retest_passed = False
        for i in range(35):
            await asyncio.sleep(3)
            r = await client.get(f"/api/repairs/{repair_id}")
            if r.status_code == 200:
                rep = r.json()
                status = rep.get("status")
                retest_passed = rep.get("retest_passed", False)
                print(f"  ... [T+{i*3}s] Repair Status: {status} | Retest Passed: {retest_passed}")
                if status in ("VERIFIED", "FAILED", "UNRESOLVED"):
                    final_repair_status = status
                    break

        print(f"\nFinal Repair Status: {final_repair_status}")
        print(f"Retest Passed: {retest_passed}")
        assert final_repair_status == "VERIFIED", f"Expected repair to be VERIFIED, got: {final_repair_status}"
        assert retest_passed is True, "Retest passed flag must be True"

        print("\n" + "=" * 60)
        print("ALL VERIFICATIONS COMPLETED SUCCESSFULLY: 100% HEALED")
        print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
