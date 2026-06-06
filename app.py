from __future__ import annotations

import datetime as dt
import json
import os
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request
import razorpay

from ai_engine import RestaurantAI


BASE_DIR = Path(__file__).resolve().parent
MENU_FILE = BASE_DIR / "menu.json"
ORDERS_FILE = BASE_DIR / "orders.json"

app = Flask(__name__)
ai = RestaurantAI(BASE_DIR)

# Razorpay Test Credentials
# Replace these with your actual test keys from Razorpay Dashboard
RAZORPAY_KEY_ID = os.environ.get('rzp_test_SyPviP5wWUTKfP')
RAZORPAY_KEY_SECRET = os.environ.get('Gh1Tc4rz3LX2Qz4g6SwJHH4s')
razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError:
        return default


def write_json(path: Path, data) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def menu_items():
    return read_json(MENU_FILE, [])


def orders():
    return read_json(ORDERS_FILE, [])


def now_parts():
    now = dt.datetime.now()
    return now.strftime("%H:%M"), now.strftime("%Y-%m-%d")


@app.route("/")
def home():
    menu = menu_items()
    all_orders = orders()
    ai.ensure_ready(menu, all_orders)
    live = ai.live_intelligence(menu, all_orders)
    featured = ai.recommend("signature popular dinner", menu, all_orders, limit=3)
    return render_template("home.html", table_id=5, live=live, featured=featured)


@app.route("/table/<int:table_id>")
def table_menu(table_id: int):
    menu = menu_items()
    all_orders = orders()
    ai.ensure_ready(menu, all_orders)
    ranked_menu = ai.rank_menu_for_context(menu, all_orders, table_id)
    live = ai.live_intelligence(menu, all_orders)
    return render_template(
        "index.html",
        table_id=table_id,
        menu=ranked_menu,
        categories=sorted({item.get("category", "other") for item in ranked_menu}),
        live=live,
    )


@app.route("/assistant/<int:table_id>")
def assistant(table_id: int):
    menu = menu_items()
    all_orders = orders()
    ai.ensure_ready(menu, all_orders)
    starter = ai.recommend("popular balanced meal", menu, all_orders, limit=1)
    return render_template("assistant.html", table_id=table_id, starter=starter[0] if starter else None)


@app.route("/ai-query", methods=["POST"])
def ai_query():
    payload = request.get_json(silent=True) or {}
    message = payload.get("message", "")
    table_id = int(payload.get("table_id") or 5)

    menu = menu_items()
    all_orders = orders()

    ai.ensure_ready(menu, all_orders)

    answer = ai.answer_guest(message, menu, all_orders, table_id)

    formatted = {
        "reply": answer.get("response", ""),
        "items": answer.get("results", []),
        "predicted_wait": answer.get("predicted_wait", 0)
    }

    return jsonify(formatted)


@app.route("/api/recommend", methods=["POST"])
def recommend_api():
    payload = request.get_json(silent=True) or {}
    query = payload.get("query", "")
    table_id = int(payload.get("table_id") or 5)
    budget = payload.get("budget")
    menu = menu_items()
    all_orders = orders()
    ai.ensure_ready(menu, all_orders)
    return jsonify(
        {
            "items": ai.recommend(
                query,
                menu,
                all_orders,
                budget=budget,
                table_id=table_id,
                limit=6,
            )
        }
    )


@app.route("/create-razorpay-order", methods=["POST"])
def create_razorpay_order():
    """Create a Razorpay order before payment"""
    payload = request.get_json(silent=True) or {}
    items = payload.get("items") or []
    table_id = int(payload.get("table_id") or 5)

    if not items:
        return jsonify({"success": False, "message": "Cart is empty"}), 400

    # Calculate total amount
    total_amount = sum(item.get("price", 0) * item.get("qty", 1) for item in items)
    amount_in_paise = int(total_amount * 100)  # Razorpay accepts amount in paise

    try:
        # Create Razorpay order
        razorpay_order = razorpay_client.order.create({
            "amount": amount_in_paise,
            "currency": "INR",
            "payment_capture": 1  # Auto capture payment
        })

        # Store order details temporarily (you might want to use a database)
        order_id = str(uuid.uuid4())[:8]
        
        return jsonify({
            "success": True,
            "razorpay_order_id": razorpay_order['id'],
            "amount": amount_in_paise,
            "currency": "INR",
            "key_id": RAZORPAY_KEY_ID,
            "order_id": order_id,
            "items": items,
            "table_id": table_id
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/verify-payment", methods=["POST"])
def verify_payment():
    """Verify Razorpay payment and create order"""
    payload = request.get_json(silent=True) or {}
    
    razorpay_order_id = payload.get("razorpay_order_id")
    razorpay_payment_id = payload.get("razorpay_payment_id")
    razorpay_signature = payload.get("razorpay_signature")
    items = payload.get("items") or []
    table_id = int(payload.get("table_id") or 5)
    order_id = payload.get("order_id")

    if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
        return jsonify({"success": False, "message": "Missing payment details"}), 400

    try:
        # Verify payment signature
        razorpay_client.utility.verify_payment_signature({
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature
        })

        # Payment verified, now create order
        menu = menu_items()
        all_orders = orders()
        ai.ensure_ready(menu, all_orders)
        eta = ai.predict_wait_time(items, table_id, all_orders, menu)
        order_time, order_date = now_parts()

        order = {
            "id": order_id,
            "items": items,
            "table_id": table_id,
            "status": "Pending",
            "time": order_time,
            "date": order_date,
            "eta": eta,
            "payment": {
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": razorpay_payment_id,
                "status": "paid"
            },
            "ml": {
                "wait_model": ai.model_card("wait_time"),
                "predicted_at": dt.datetime.now().isoformat(timespec="seconds"),
            },
        }

        all_orders.append(order)
        write_json(ORDERS_FILE, all_orders)
        
        return jsonify({
            "success": True,
            "order_id": order["id"],
            "eta": eta,
            "message": f"Payment successful! Order placed. ML predicted wait time: {eta} mins",
        })
    except razorpay.errors.SignatureVerificationError:
        return jsonify({"success": False, "message": "Payment verification failed"}), 400
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/place-order", methods=["POST"])
def place_order():
    """Legacy endpoint - kept for backward compatibility"""
    payload = request.get_json(silent=True) or {}
    items = payload.get("items") or []
    table_id = int(payload.get("table_id") or 5)

    if not items:
        return jsonify({"success": False, "message": "Cart is empty"}), 400

    menu = menu_items()
    all_orders = orders()
    ai.ensure_ready(menu, all_orders)
    eta = ai.predict_wait_time(items, table_id, all_orders, menu)
    order_time, order_date = now_parts()

    order = {
        "id": str(uuid.uuid4())[:8],
        "items": items,
        "table_id": table_id,
        "status": "Pending",
        "time": order_time,
        "date": order_date,
        "eta": eta,
        "ml": {
            "wait_model": ai.model_card("wait_time"),
            "predicted_at": dt.datetime.now().isoformat(timespec="seconds"),
        },
    }

    all_orders.append(order)
    write_json(ORDERS_FILE, all_orders)
    return jsonify(
        {
            "success": True,
            "order_id": order["id"],
            "eta": eta,
            "message": f"Order placed. ML predicted wait time: {eta} mins",
        }
    )


@app.route("/order-status/<order_id>")
def order_status_page(order_id: str):
    return render_template("status.html", order_id=order_id)


@app.route("/api/order-status/<order_id>")
def order_status_api(order_id: str):
    order = next((item for item in orders() if item.get("id") == order_id), None)
    if not order:
        return jsonify({"error": "Order not found"}), 404
    return jsonify(order)


@app.route("/update-status/<order_id>", methods=["POST"])
def update_status(order_id: str):
    payload = request.get_json(silent=True) or {}
    new_status = payload.get("status")
    if new_status not in {"Pending", "Preparing", "Ready", "Completed"}:
        return jsonify({"success": False, "message": "Invalid status"}), 400

    all_orders = orders()
    for order in all_orders:
        if order.get("id") == order_id:
            order["status"] = new_status
            if new_status == "Completed":
                order["completed_time"] = dt.datetime.now().strftime("%H:%M")
            break
    write_json(ORDERS_FILE, all_orders)
    return jsonify({"success": True})


@app.route("/dashboard")
def dashboard():
    menu = menu_items()
    all_orders = orders()
    ai.ensure_ready(menu, all_orders)
    return render_template("dashboard.html", live=ai.live_intelligence(menu, all_orders))


@app.route("/get-requests")
def get_requests():
    return jsonify(orders())


@app.route("/api/analytics")
def analytics():
    menu = menu_items()
    all_orders = orders()
    ai.ensure_ready(menu, all_orders)
    return jsonify(ai.analytics(menu, all_orders))


@app.route("/api/ml-status")
def ml_status():
    menu = menu_items()
    all_orders = orders()
    ai.ensure_ready(menu, all_orders)
    return jsonify(ai.status())


@app.route("/queue")
def queue_page():
    """Kitchen queue dashboard — shows all orders, staff can update status live."""
    all_orders = orders()
    return render_template("queue.html", orders=all_orders)


@app.route("/api/queue")
def queue_api():
    """Returns only active (non-completed) orders as JSON."""
    all_orders = orders()
    active = [o for o in all_orders if o.get("status") != "Completed"]
    return jsonify(active)


@app.route("/api/queue-all")
def queue_all_api():
    """Returns all orders (active + completed) as JSON for stats refresh."""
    return jsonify(orders())


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5001)))

