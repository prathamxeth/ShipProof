import asyncio
import sys
import httpx

STORE_URL = "http://127.0.0.1:3005"
CONSOLE_URL = "http://localhost:3000"

async def test_full_store_flow():
    print("==================================================")
    print("1. TESTING TARGET STORE (http://127.0.0.1:3005)")
    print("==================================================")
    
    async with httpx.AsyncClient(base_url=STORE_URL, follow_redirects=True) as client:
        # Ensure defect is initially disabled
        await client.post("/api/defect/toggle", params={"enable": False})

        # Step 1: Catalog
        res = await client.get("/")
        assert res.status_code == 200, f"Catalog failed: {res.status_code}"
        assert "Acme Voyager Store" in res.text, "Brand title missing in catalog"
        assert "Featured Products" in res.text, "Products header missing"
        assert 'id="add-to-cart-1"' in res.text, "Add to cart button missing"
        print("✓ Step 1: Catalog loaded cleanly with liquid glass branding.")

        # Step 2: Add to Cart (Headphones $99)
        res = await client.post("/cart/add", data={"product_id": 1})
        assert res.status_code == 200, f"Add to cart failed: {res.status_code}"
        assert "Your Shopping Bag" in res.text, "Cart header missing"
        assert "$99.00" in res.text, "Item price missing in cart"
        assert 'id="checkout-btn"' in res.text, "Checkout button missing in cart"
        print("✓ Step 2: Product added to bag. Cart loaded with $99.00 subtotal.")

        # Step 3: Update Quantity to 2
        res = await client.post("/cart/update", data={"product_id": 1, "quantity": 2})
        assert res.status_code == 200, f"Update cart failed: {res.status_code}"
        assert "$198.00" in res.text, "Subtotal did not update to $198.00"
        print("✓ Step 3: Quantity updated to 2. Subtotal calculated to $198.00.")

        # Step 4: Checkout Form
        res = await client.get("/checkout")
        assert res.status_code == 200, f"Checkout failed: {res.status_code}"
        assert "Express Checkout" in res.text, "Checkout header missing"
        assert "$198.00" in res.text, "Order total missing on checkout"
        assert 'id="place-order-btn"' in res.text, "Place order button missing"
        print("✓ Step 4: Express checkout form loaded with matching $198.00 total.")

        # Step 5: Place Order
        res = await client.post("/checkout", data={
            "full_name": "Alex Johnson",
            "email": "alex@example.com",
            "address": "123 AI Boulevard, Suite 400, San Francisco, CA"
        })
        assert res.status_code == 200, f"Order placement failed: {res.status_code}"
        assert "Order Placed Successfully!" in res.text, "Confirmation title missing"
        assert 'id="order-number"' in res.text, "Order reference identifier missing"
        assert 'id="continue-shopping-btn"' in res.text, "Continue shopping button missing"
        print("✓ Step 5: Order successfully placed! Confirmation card generated with unique ORD number.")

        # Step 6: Test Defect State
        # Add item to cart so cart has items to show checkout button
        await client.post("/cart/add", data={"product_id": 1})
        
        # Toggle defect on store (POST)
        res = await client.post("/api/defect/toggle", params={"enable": True})
        res_cart = await client.get("/cart")
        assert 'id="checkout-btn-broken"' in res_cart.text, "Broken checkout button missing when defect active"
        assert "DEFECT ACTIVE" in res_cart.text, "Defect indicator badge missing"
        print("✓ Step 6: Defect injection verified. Checkout button rendered as disabled and defect badge displayed.")

        # Restore normal state (POST)
        await client.post("/api/defect/toggle", params={"enable": False})
        res_cart_healed = await client.get("/cart")
        assert 'id="checkout-btn"' in res_cart_healed.text, "Checkout button not restored after clear"
        print("✓ Step 7: Defect healed. Active checkout button restored.")

async def test_backend_and_guardian_api():
    print("\n==================================================")
    print("2. TESTING SHIPPROOF AI GUARDIAN CONSOLE (http://localhost:3000)")
    print("==================================================")
    
    async with httpx.AsyncClient(base_url=CONSOLE_URL, follow_redirects=True) as client:
        # Establish console session with demo key
        login_res = await client.post("/api/auth/login", json={"key": "demo"})
        assert login_res.status_code == 200, f"Session creation failed: {login_res.status_code}"
        print("✓ Session: Authenticated console session initialized.")

        # Health
        res = await client.get("/api/health")
        assert res.status_code == 200, f"Health check failed: {res.status_code}"
        health = res.json()
        print(f"✓ Health: status={health.get('status')}, kane_cli={health.get('kane_cli_installed')}")

        # Overview stats
        res = await client.get("/api/overview")
        assert res.status_code == 200, f"Overview stats failed: {res.status_code}"
        overview = res.json()
        print(f"✓ Overview: total_runs={overview.get('total_runs')}, verified_repairs={overview.get('repairs_verified')}")

        # Revenue Guard status
        res = await client.get("/api/guard/status")
        assert res.status_code == 200, f"Guard status failed: {res.status_code}"
        guard = res.json()
        print(f"✓ Guard: enabled={guard.get('enabled')}, interval={guard.get('interval_label')}, protected=${guard.get('revenue_protected')}")

        # Revenue Guard manual probe trigger
        res = await client.post("/api/guard/probe")
        assert res.status_code == 200, f"Guard probe failed: {res.status_code}"
        probe = res.json()
        print(f"✓ Guard Probe: run_id={probe.get('run_id')}, title={probe.get('title')}")

        # List runs
        res = await client.get("/api/runs?limit=5")
        assert res.status_code == 200, f"List runs failed: {res.status_code}"
        runs = res.json()
        print(f"✓ Runs Feed: {runs.get('total', len(runs.get('items', [])))} verification runs logged.")

        # List repairs
        res = await client.get("/api/repairs")
        assert res.status_code == 200, f"List repairs failed: {res.status_code}"
        repairs = res.json()
        print(f"✓ Repairs: {len(repairs)} repair jobs registered.")

async def main():
    try:
        await test_full_store_flow()
        await test_backend_and_guardian_api()
        print("\n==================================================")
        print("ALL PIPELINES, BUTTONS, & ACTIONS TESTED: 100% PASS")
        print("==================================================")
    except AssertionError as e:
        print(f"\n❌ Assertion failed: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n❌ Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
