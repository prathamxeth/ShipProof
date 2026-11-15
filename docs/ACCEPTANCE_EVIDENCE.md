# ShipProof — Acceptance Evidence Inventory

**Milestone:** 4.1 & 4.2 Live Product Acceptance  
**Audit Date:** November 16, 2026  
**Auditor:** Antigravity IDE Autonomous Engineering Agent  
**Workspace:** `/Users/pratham/Projects/ShipProof`  

This document serves as the verified, immutable audit record of all physical evidence files, browser sessions, screenshot artifacts, and test execution results collected during live acceptance testing.

---

## 1. Verified Session & Execution Identifiers

All identifiers below reference physical session directories managed by Kane CLI at `~/.testmuai/kaneai/sessions/` and database records in `backend/data/shipproof.db`.

| Stage | Identifier Key | Exact Value | On-Disk Path / Location |
| :--- | :--- | :--- | :--- |
| **Frontend Verification** | Kane Session ID | `e1190cb5-de67-425d-a046-95100e89c887` | `/Users/pratham/.testmuai/kaneai/sessions/e1190cb5-de67-425d-a046-95100e89c887` |
| **Frontend Verification** | Evidence Pack File | `fca83f2a-6521-471c-bc03-21247b77d44a.evidence` | `/Users/pratham/.testmuai/kaneai/sessions/e1190cb5-de67-425d-a046-95100e89c887/evidence/fca83f2a-6521-471c-bc03-21247b77d44a.evidence` (1,111,174 bytes) |
| **Initial Defect Run** | Run ID | `4d73d80c-9925-4325-935b-e9e584c2b21c` | Database: `verification_runs` table |
| **Initial Defect Run** | Kane Session ID | `0268bdf3-c07d-4412-bee7-b0693c315ac0` | `/Users/pratham/.testmuai/kaneai/sessions/0268bdf3-c07d-4412-bee7-b0693c315ac0` |
| **Initial Defect Run** | Evidence Pack File | `58a1a844-ceb1-4bd8-8b50-562ee81d526d.evidence` | `/Users/pratham/.testmuai/kaneai/sessions/0268bdf3-c07d-4412-bee7-b0693c315ac0/evidence/58a1a844-ceb1-4bd8-8b50-562ee81d526d.evidence` (257,594 bytes) |
| **Repair Workflow** | Repair Session ID | `a28b8bd0-a536-4a7a-8578-b3e30c55a46e` | Database: `repair_records` table |
| **Repair Workflow** | Job Workspace Folder | `.shipproof/repairs/a28b8bd0-a536-4a7a-8578-b3e30c55a46e/` | `/Users/pratham/Projects/ShipProof/.shipproof/repairs/a28b8bd0-a536-4a7a-8578-b3e30c55a46e/` (`job.json`, `prompt.md`) |
| **Retest Run** | Run ID | `19ba2e21-b7a9-4364-831c-049f3580e7de` | Database: `verification_runs` table |
| **Retest Run** | Kane Session ID | `422a7723-7317-46a4-bcbd-0da2db3e37cd` | `/Users/pratham/.testmuai/kaneai/sessions/422a7723-7317-46a4-bcbd-0da2db3e37cd` |
| **Retest Run** | Evidence Pack File | `4f970c69-eac3-40b0-9a4b-d0119982419f.evidence` | `/Users/pratham/.testmuai/kaneai/sessions/422a7723-7317-46a4-bcbd-0da2db3e37cd/evidence/4f970c69-eac3-40b0-9a4b-d0119982419f.evidence` (440,788 bytes) |

---

## 2. Screenshot Artifact Inventory

The following screenshots were captured live during browser navigation across the Next.js frontend by Kane CLI session `e1190cb5-de67-425d-a046-95100e89c887` and extracted to `docs/screenshots/`:

| Filename | File Size | UI Route | Description |
| :--- | :--- | :--- | :--- |
| `1-0-1_screenshot.jpg` | 29 KB | `/` (Dashboard) | Initial browser load of ShipProof Overview Dashboard |
| `2-0-2_screenshot.jpg` | 29 KB | `/` (Dashboard) | Inspection of KPI metric cards and header navigation |
| `3-0-3_screenshot.jpg` | 29 KB | `/` (Dashboard) | Verification of recent activity feed and action buttons |
| `4-0-4_screenshot.jpg` | 29 KB | `/` (Dashboard) | Pre-navigation state before clicking "Verification Runs" |
| `5-0-5_screenshot.jpg` | 28 KB | `/runs` | Verification Runs table loaded with run history |
| `5-0-5_annotated.png` | 172 KB | `/runs` | Kane annotated target element for nav link click |
| `6-0-6_screenshot.jpg` | 42 KB | `/runs` | Filter and search controls on verification runs table |
| `7-0-7_screenshot.jpg` | 42 KB | `/runs` | Inspection of status pills and run metadata |
| `8-0-8_screenshot.jpg` | 42 KB | `/runs` | Pagination and step count validation |
| `9-0-9_screenshot.jpg` | 42 KB | `/runs` | Pre-navigation state before clicking "Repair Studio" |
| `10-0-10_screenshot.jpg`| 37 KB | `/repairs` | Repair Studio interface displaying active repair sessions |
| `10-0-10_annotated.png`| 317 KB| `/repairs` | Kane annotated elements identifying repair cards and actions |
| `11-0-11_screenshot.jpg`| 43 KB | `/repairs` | Inspection of repair lifecycle states and diff review entries |
| `12-0-12_screenshot.jpg`| 26 KB | `/projects` | Projects management screen listing registered projects |
| `12-0-12_annotated.png`| 82 KB | `/projects` | Kane annotated target element for projects navigation |
| `13-0-13_screenshot.jpg`| 42 KB | `/settings` | Settings & System Diagnostics page |
| `13-0-13_annotated.png`| 178 KB| `/settings` | Kane annotated element for Settings nav link |
| `14-0-14_screenshot.jpg`| 43 KB | `/settings` | Diagnostic status cards showing Kane CLI authenticated |
| `screenshot.jpg` | 42 KB | `/settings` | Final browser viewport snapshot upon test completion |
| `annotated.png` | 172 KB| `/settings` | Final terminal step visual confirmation |

---

## 3. Actual Executed Commands & Verifiable Outcomes

### A. Kane CLI Frontend Verification
```bash
kane-cli run \
  --url "http://localhost:3000" \
  --objective "Verify the homepage title is 'ShipProof', click on 'Verification Runs' nav link and verify runs are listed, then click 'Repair Studio', 'Projects', and 'Settings' to ensure all pages load without error." \
  --agent \
  --headless
```
- **Session:** `e1190cb5-de67-425d-a046-95100e89c887`
- **Duration:** 79.1 seconds
- **Steps:** 14 executed / 14 passed / 0 failed
- **Exit Code:** `0`
- **Terminal Event:** `{"type": "run_end", "status": "passed", "duration": 79.1, "exit_code": 0}`

### B. Defect Introduction & Kane Initial Failure Run
```bash
# Defect enabled in demo_targets/sample_store/config.json
kane-cli run \
  --url "http://127.0.0.1:3005/product/1" \
  --objective "Click 'Add to Cart', then in the cart click 'Proceed to Checkout', and verify that 'Secure Checkout' is displayed." \
  --agent \
  --headless
```
- **ShipProof Run ID:** `4d73d80c-9925-4325-935b-e9e584c2b21c`
- **Kane Session:** `0268bdf3-c07d-4412-bee7-b0693c315ac0`
- **Duration:** 47.9 seconds
- **Steps:** 3 executed / 2 passed / 1 failed
- **Failure Cause:** Checkout button had broken ID (`checkout-btn-broken`) and `disabled` attribute.
- **Exit Code:** `1`
- **Terminal Event:** `{"type": "run_end", "status": "failed", "duration": 47.9, "exit_code": 1}`

### C. Antigravity IDE Agent Repair & Retest Run
```bash
# Repair applied by Antigravity IDE Agent in cart.html and config.json
# Approved via POST /api/repairs/a28b8bd0-a536-4a7a-8578-b3e30c55a46e/approve
# Automatic re-test triggered:
kane-cli run \
  --url "http://127.0.0.1:3005/product/1" \
  --objective "Click 'Add to Cart', then in the cart click 'Proceed to Checkout', and verify that 'Secure Checkout' is displayed." \
  --agent \
  --headless
```
- **ShipProof Retest Run ID:** `19ba2e21-b7a9-4364-831c-049f3580e7de`
- **Kane Session:** `422a7723-7317-46a4-bcbd-0da2db3e37cd`
- **Duration:** 59.7 seconds
- **Steps:** 6 executed / 6 passed / 0 failed
- **Exit Code:** `0`
- **Terminal Event:** `{"type": "run_end", "status": "passed", "duration": 59.7, "exit_code": 0}`
- **Repair Record Final Status:** `VERIFIED` (`retest_passed: true`)
- **Parent Run Status:** Updated from `failed` to `verified` (`repaired: true`)
