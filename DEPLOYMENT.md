# ShipProof — Production Cloud Deployment Guide (Vercel & Render)

This guide walks you through deploying **ShipProof** permanently to **Vercel** (Frontend) and **Render** (Backend & Store), replacing temporary local tunnels with high-availability cloud URLs.

---

## Architecture Overview

```
                      ┌────────────────────────────────────────┐
                      │              USER / JUDGE              │
                      └──────────────────┬─────────────────────┘
                                         │
                                         ▼
                     ┌──────────────────────────────────────────┐
                     │           VERCEL (Edge Network)          │
                     │          https://shipproof.vercel.app    │
                     │  - Next.js 16 (App Router + Tailwind)    │
                     │  - Springlight Glass UI & Real Viewport  │
                     └──────────────────┬───────────────────────┘
                                        │ /api/* rewrites
                                        ▼
                     ┌──────────────────────────────────────────┐
                     │          RENDER (Cloud Container)        │
                     │    https://shipproof-backend.onrender.com │
                     │  - FastAPI Backend (Port 8000)           │
                     │  - Acme Storefront (Port 3005)           │
                     │  - Kane CLI + Chromium Autonomous Shopper│
                     │  - Persistent Disk (/app/backend/data)   │
                     └──────────────────────────────────────────┘
```

---

## Step 1: Push Code to GitHub

All deployment configuration files (`Dockerfile`, `render.yaml`, `vercel.json`, `scripts/start_production.sh`) have been committed.

Push to your remote GitHub repository:

```bash
git push origin main
```

---

## Step 2: Deploy Backend to Render (1-Click Blueprint)

1. Sign in to [Render Dashboard](https://dashboard.render.com/).
2. Click **New +** (top right) and select **Blueprint**.
3. Select your repository: **`prathamxeth/ShipProof`**.
4. Render will detect `render.yaml` automatically and configure:
   - **Service Name**: `shipproof-backend`
   - **Runtime**: Docker (builds via root `Dockerfile`)
   - **Environment Variables**:
     - `PORT`: `8000`
     - `ENVIRONMENT`: `production`
     - `WORKER_EXECUTION_MODE`: `subprocess`
     - `ALLOW_LOCAL_TARGETS`: `true`
     - `SHIPPROOF_BETA_KEY`: `e2eb14edb1e819e5ac2250c4979c94181cd51419f29edf3a4f7279822d8c9f6a`
     - `CORS_ORIGINS`: `http://localhost:3000,http://127.0.0.1:3000,https://*.vercel.app`
   - **Persistent Disk**: 1GB mounted at `/app/backend/data` (keeps SQLite database and test runs safe across reboots).
5. Click **Apply**.
6. When deployment finishes, copy your Render URL (e.g. `https://shipproof-backend.onrender.com`).

---

## Step 3: Deploy Frontend to Vercel

### Option A: Via Vercel Web Dashboard (Recommended)

1. Sign in to [Vercel](https://vercel.com/new).
2. Click **Import** next to your **`ShipProof`** repository.
3. Configure the project:
   - **Framework Preset**: Next.js
   - **Root Directory**: Click *Edit* and select **`frontend`**
   - **Build Command**: `npm run build`
   - **Output Directory**: `.next`
4. Expand **Environment Variables** and add:

   | Variable Name | Value |
   | :--- | :--- |
   | `NEXT_PUBLIC_BACKEND_URL` | `https://shipproof-backend.onrender.com` (Your Render URL from Step 2) |
   | `SHIPPROOF_BETA_KEY` | `e2eb14edb1e819e5ac2250c4979c94181cd51419f29edf3a4f7279822d8c9f6a` |
   | `NEXT_PUBLIC_STORE_URL` | `http://127.0.0.1:3005` (or public URL if exposed) |

5. Click **Deploy**.

### Option B: Via Vercel CLI

From your terminal:

```bash
cd frontend
npx vercel
```
Follow the interactive prompts to link and deploy your project.
