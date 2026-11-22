# ShipProof — 1-Click Production Cloud Deployment on Render

You can deploy the **entire ShipProof stack** (Next.js 16 Frontend + FastAPI Backend + Acme Voyager Storefront + Autonomous Chromium Agent) as a **single unified Web Service on Render**.

---

## Unified Architecture

```
                    ┌──────────────────────────────────────────────┐
                    │                 USER / JUDGE                 │
                    └──────────────────────┬───────────────────────┘
                                           │
                                           ▼ (Single Public URL)
                    ┌──────────────────────────────────────────────┐
                    │            RENDER WEB SERVICE                │
                    │         https://shipproof.onrender.com       │
                    │                                              │
                    │  ┌────────────────────────────────────────┐  │
                    │  │ Next.js 16 (Port $PORT / 10000)        │  │
                    │  │ - Springlight Glass UI                 │  │
                    │  │ - Server rewrites /api/* to :8000      │  │
                    │  └──────────────────┬─────────────────────┘  │
                    │                     │                        │
                    │  ┌──────────────────▼─────────────────────┐  │
                    │  │ FastAPI Backend (Internal :8000)       │  │
                    │  │ - SQLite Database                      │  │
                    │  │ - AI Self-Healing & Verification Engine│  │
                    │  └──────────────────┬─────────────────────┘  │
                    │                     │                        │
                    │  ┌──────────────────▼─────────────────────┐  │
                    │  │ Kane CLI + Chromium Shopper Agent      │  │
                    │  │ - Headless browser automation          │  │
                    │  │ - Audits Acme Store (Internal :3005)   │  │
                    │  └────────────────────────────────────────┘  │
                    └──────────────────────────────────────────────┘
```

---

## 1-Click Deployment Instructions

### Step 1: Push latest commits to GitHub
In your local terminal, push the latest code:
```bash
git push origin main
```

---

### Step 2: Deploy on Render via Blueprint (2 minutes)

1. Sign in to [Render Dashboard](https://dashboard.render.com/).
2. In the top right, click **New +** $\rightarrow$ **Blueprint**.
3. Connect your GitHub repository: **`prathamxeth/ShipProof`**.
4. Render automatically detects `render.yaml` and sets up:
   - **Service Name**: `shipproof`
   - **Plan**: `Free` (or Starter)
   - **Runtime**: Docker (builds the all-in-one container with Next.js, Python 3.12, Node 20, Kane CLI, and Chromium)
5. Click **Apply**.
6. Render will build the container and deploy it.
7. Once the build completes, your entire product will be live at:
   `https://shipproof-xxxx.onrender.com` (or your custom service name).

---

## What Happens When Deployed

- **Single Domain**: Everything runs under one public URL. No CORS restrictions, no cookie synchronization issues, and no separate services to configure.
- **Mission Control**: The judge visits `https://your-app.onrender.com` to see the Springlight dashboard and test history.
- **Autonomous Secret Shopper**: The Kane CLI runs Chromium directly inside the Linux container, testing the checkout flow on `http://127.0.0.1:3005`.
- **Live Self-Healing Demo**: Clicking **Break Store Checkout** injects the defect; clicking **Test Customer Order** detects the failure and auto-generates the repair in real time.
