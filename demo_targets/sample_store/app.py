import json
import uuid
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, Form, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

APP_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"
CONFIG_FILE = APP_DIR / "config.json"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app = FastAPI(title="ShipProof Sample Store", description="Target application for closed-loop verification")

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# In-memory product catalog
PRODUCTS = {
    1: {
        "id": 1,
        "name": "Voyager Shoes",
        "price": 99.00,
        "icon": "👟",
        "description": "Ultra-lightweight breathable athletic performance shoes engineered for daily endurance.",
        "details": "Constructed with adaptive woven mesh, dual-density responsive cushioning, and high-traction rubber outsole. Engineered for optimal comfort."
    },
    2: {
        "id": 2,
        "name": "Ergonomic Mechanical Keyboard",
        "price": 149.00,
        "icon": "⌨️",
        "description": "Hot-swappable tactile switches with customizable RGB lighting and aluminum frame.",
        "details": "Designed for maximum typing comfort and coding efficiency. Includes sound-dampening foam, PBT doubleshot keycaps, and USB-C detachable cable."
    },
    3: {
        "id": 3,
        "name": "Precision Wireless Gaming Mouse",
        "price": 59.00,
        "icon": "🖱️",
        "description": "Ultra-lightweight 60g ergonomic design with 26K DPI optical sensor.",
        "details": "Lag-free 2.4GHz wireless connection with optical switches rated for 90 million clicks."
    }
}

# In-memory carts: {session_id: {product_id: quantity}}
CARTS: Dict[str, Dict[int, int]] = {}

def get_config() -> Dict[str, Any]:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"defect_enabled": False}

def set_config(cfg: Dict[str, Any]):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

def get_session_id(request: Request, response: Optional[Response] = None) -> str:
    sid = request.cookies.get("store_session")
    if not sid:
        sid = str(uuid.uuid4())
        if response:
            response.set_cookie("store_session", sid, httponly=True)
    return sid

@app.get("/", response_class=HTMLResponse)
async def catalog(request: Request):
    sid = get_session_id(request)
    cart = CARTS.get(sid, {})
    cart_count = sum(cart.values())
    cfg = get_config()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "title": "ShipProof Tech Store — Catalog",
            "products": list(PRODUCTS.values()),
            "cart_count": cart_count,
            "defect_enabled": cfg.get("defect_enabled", False)
        }
    )

@app.get("/product/{product_id}", response_class=HTMLResponse)
async def product_detail(product_id: int, request: Request):
    product = PRODUCTS.get(product_id)
    if not product:
        return RedirectResponse("/", status_code=303)

    sid = get_session_id(request)
    cart = CARTS.get(sid, {})
    cart_count = sum(cart.values())
    cfg = get_config()

    return templates.TemplateResponse(
        request=request,
        name="product.html",
        context={
            "title": f"{product['name']} — ShipProof Store",
            "product": product,
            "cart_count": cart_count,
            "defect_enabled": cfg.get("defect_enabled", False)
        }
    )

@app.post("/cart/add")
async def add_to_cart(request: Request, product_id: int = Form(...)):
    response = RedirectResponse("/cart", status_code=303)
    sid = get_session_id(request, response)
    
    if sid not in CARTS:
        CARTS[sid] = {}
    CARTS[sid][product_id] = CARTS[sid].get(product_id, 0) + 1
    return response

@app.get("/cart", response_class=HTMLResponse)
async def view_cart(request: Request):
    sid = get_session_id(request)
    cart = CARTS.get(sid, {})
    
    items = []
    subtotal = 0.0
    for pid, qty in cart.items():
        if pid in PRODUCTS and qty > 0:
            prod = PRODUCTS[pid]
            total = prod["price"] * qty
            subtotal += total
            items.append({"product": prod, "quantity": qty, "total": total})

    cfg = get_config()
    defect_enabled = cfg.get("defect_enabled", False)

    return templates.TemplateResponse(
        request=request,
        name="cart.html",
        context={
            "title": "Shopping Cart — ShipProof Store",
            "items": items,
            "subtotal": subtotal,
            "cart_count": sum(cart.values()),
            "defect_enabled": defect_enabled
        }
    )

@app.post("/cart/update")
async def update_cart(request: Request, product_id: int = Form(...), quantity: int = Form(...)):
    sid = get_session_id(request)
    if sid in CARTS:
        if quantity <= 0:
            CARTS[sid].pop(product_id, None)
        else:
            CARTS[sid][product_id] = quantity
    return RedirectResponse("/cart", status_code=303)

@app.get("/checkout", response_class=HTMLResponse)
async def checkout_form(request: Request):
    sid = get_session_id(request)
    cart = CARTS.get(sid, {})
    subtotal = sum(PRODUCTS[pid]["price"] * qty for pid, qty in cart.items() if pid in PRODUCTS)

    cfg = get_config()
    return templates.TemplateResponse(
        request=request,
        name="checkout.html",
        context={
            "title": "Checkout — ShipProof Store",
            "subtotal": subtotal,
            "cart_count": sum(cart.values()),
            "defect_enabled": cfg.get("defect_enabled", False)
        }
    )

@app.post("/checkout")
async def process_checkout(request: Request, full_name: str = Form(...), email: str = Form(...), address: str = Form(...)):
    sid = get_session_id(request)
    CARTS.pop(sid, None)
    order_id = f"ORD-{uuid.uuid4().hex[:6].upper()}"
    return RedirectResponse(f"/order-confirmation?order_id={order_id}", status_code=303)

@app.get("/order-confirmation", response_class=HTMLResponse)
async def order_confirmation(request: Request, order_id: str = "ORD-SUCCESS"):
    return templates.TemplateResponse(
        request=request,
        name="confirmation.html",
        context={
            "title": "Order Confirmed — ShipProof Store",
            "order_id": order_id,
            "cart_count": 0,
            "defect_enabled": False
        }
    )

# --- Defect Management Endpoints ---
@app.get("/api/defect")
async def get_defect_status():
    return get_config()

@app.post("/api/defect/toggle")
async def toggle_defect(enable: Optional[bool] = None):
    cfg = get_config()
    if enable is not None:
        cfg["defect_enabled"] = enable
    else:
        cfg["defect_enabled"] = not cfg.get("defect_enabled", False)
    set_config(cfg)
    return cfg

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("demo_targets.sample_store.app:app", host="127.0.0.1", port=3005, reload=False)
