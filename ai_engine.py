from __future__ import annotations

import datetime as dt
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.neighbors import NearestNeighbors
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


MODEL_VERSION = "2026.04.restaurant-intelligence.v2"
ACTIVE_STATUSES = {"Pending", "Preparing", "Ready"}
RUPEE_RE = re.compile(r"(?:under|below|less than|within|upto|up to)?\s*(?:₹|rs\.?|inr)?\s*(\d{2,5})", re.I)


class RestaurantAI:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.models_dir = self.base_dir / "models"
        self.models_dir.mkdir(exist_ok=True)
        self._cache = {}

    def ensure_ready(self, menu: list[dict], orders: list[dict]) -> None:
        required = ["recommendation.joblib", "intent.joblib", "wait_time.joblib"]
        meta = self._read_json(self.models_dir / "model_meta.json", {})
        rec_rows = (
            meta.get("models", {})
            .get("recommendation", {})
            .get("trained_rows", 0)
        )
        stale = meta.get("version") != MODEL_VERSION or rec_rows < 50
        if stale or not all((self.models_dir / name).exists() for name in required):
            self.train(menu, orders)

    def train(self, menu: list[dict], orders: list[dict]) -> dict:
        self.models_dir.mkdir(exist_ok=True)
        recommendation = self._train_recommendation(menu)
        intent = self._train_intent()
        wait = self._train_wait_time(menu, orders)
        meta = {
            "version": MODEL_VERSION,
            "trained_at": dt.datetime.now().isoformat(timespec="seconds"),
            "menu_items": len(menu),
            "historical_orders": len(orders),
            "models": {
                "recommendation": recommendation["card"],
                "intent": intent["card"],
                "wait_time": wait["card"],
            },
        }
        self._write_json(self.models_dir / "model_meta.json", meta)
        self._cache.clear()
        return meta

    def recommend(
        self,
        query: str,
        menu: list[dict],
        orders: list[dict],
        budget: int | None = None,
        table_id: int | None = None,
        limit: int = 4,
    ) -> list[dict]:
        self.ensure_ready(menu, orders)
        model = self._load("recommendation.joblib")
        if not menu:
            return []

        clean_query = self._enrich_query(query, table_id)
        budget = budget or self.extract_budget(query)
        query_vec = model["vectorizer"].transform([clean_query])
        similarities = cosine_similarity(query_vec, model["matrix"])[0]
        popularity = self._popularity_scores(orders)

        ranked = []
        for idx, item_id in enumerate(model["menu_ids"]):
            item = next((dish for dish in menu if int(dish.get("id", -1)) == int(item_id)), None)
            if not item:
                continue
            if budget and int(item.get("price", 0)) > int(budget):
                continue
            price_fit = self._price_fit(item.get("price", 0), budget)
            order_boost = popularity.get(self._item_name(item), 0.0)
            score = float((similarities[idx] * 0.74) + (order_boost * 0.18) + (price_fit * 0.08))
            clone = dict(item)
            clone["ml_score"] = round(score, 4)
            clone["match_percent"] = int(max(52, min(98, 54 + score * 44)))
            clone["reason"] = self._reason_for_match(query, item, score)
            ranked.append(clone)

        ranked.sort(key=lambda dish: dish["ml_score"], reverse=True)
        return ranked[:limit]

    def rank_menu_for_context(self, menu: list[dict], orders: list[dict], table_id: int) -> list[dict]:
        hour = dt.datetime.now().hour
        meal_period = "lunch" if 11 <= hour < 16 else "dinner" if 16 <= hour < 23 else "light snacks"
        ranked = self.recommend(f"popular {meal_period} guest favourite", menu, orders, table_id=table_id, limit=len(menu))
        seen = {item["id"] for item in ranked}
        for item in menu:
            if item.get("id") not in seen:
                clone = dict(item)
                clone["ml_score"] = 0.05
                clone["match_percent"] = 56
                clone["reason"] = "Baseline menu item"
                ranked.append(clone)
        return ranked

    def predict_wait_time(self, items: list[dict], table_id: int, orders: list[dict], menu: list[dict]) -> int:
        self.ensure_ready(menu, orders)
        model = self._load("wait_time.joblib")
        row = self._wait_features(items, table_id, orders, menu)
        prediction = float(model["pipeline"].predict(pd.DataFrame([row]))[0])
        
        if prediction > 70:
            prediction = 70 + (prediction - 70) * 0.3  # compress high values

        return int(max(4, round(prediction)))

    def answer_guest(self, message: str, menu: list[dict], orders: list[dict], table_id: int) -> dict:
        self.ensure_ready(menu, orders)

        intent = self._predict_intent(message)

        if intent not in ["greeting", "wait_time", "order", "diet", "recommendation"]:
            intent = "recommendation"

        budget = self.extract_budget(message)

        msg = message.lower()
        filtered_menu = menu

        if "dessert" in msg:
            filtered_menu = [item for item in menu if item.get("category") == "desserts"]

        elif "starter" in msg:
            filtered_menu = [item for item in menu if item.get("category") == "starters"]

        elif "main" in msg:
            filtered_menu = [item for item in menu if item.get("category") == "mains"]

        if "spicy" in msg:
            filtered_menu = [item for item in filtered_menu if "spicy" in item.get("tags", [])]

        elif "healthy" in msg:
            filtered_menu = [item for item in filtered_menu if "healthy" in item.get("tags", [])]

        elif "sweet" in msg:
            filtered_menu = [item for item in filtered_menu if "sweet" in item.get("tags", [])]

        elif "veg" in msg:
            filtered_menu = [item for item in filtered_menu if "veg" in item.get("tags", [])]

        if not filtered_menu:
            filtered_menu = menu

        results = self.recommend(
            message,
            filtered_menu,
            orders,
            budget=budget,
            table_id=table_id,
            limit=3
        )

        sample_wait = self.predict_wait_time(
            results[:1] or menu[:1],
            table_id,
            orders,
            menu
        ) if menu else 0

        if intent == "greeting":
            response = "Welcome to LUME. Tell me your mood, budget, spice level, or diet preference."

        elif intent == "wait_time":
            response = f"Estimated wait time is about {sample_wait} minutes for table {table_id}."

        elif intent == "order":
            response = "Here are some items you can order. Tap any item to proceed."

        elif intent == "diet":
            if results:
                names = ", ".join(item["name"] for item in results[:2])
                response = f"For your preference, I recommend {names}."
            else:
                response = "I couldn't find strong matches. Try 'veg', 'healthy', or 'low calorie'."

        elif results:
            names = ", ".join(item["name"] for item in results[:2])
            response = f"Based on your request for '{message}', I recommend {names}."

        else:
            response = "I couldn't find a good match. Try 'spicy veg under 200' or 'best dessert'."

        return {
            "intent": intent,
            "response": response,
            "results": results,
            "predicted_wait": sample_wait,
            "model": self.model_card("recommendation"),
        }

    def live_intelligence(self, menu: list[dict], orders: list[dict]) -> dict:
        active = [order for order in orders if order.get("status") in ACTIVE_STATUSES]
        active_items = sum(len(order.get("items") or [order]) for order in active)
        sample_items = menu[:1] or []
        wait = self.predict_wait_time(sample_items, 5, orders, menu) if menu else 0
        top = self._top_dishes(orders, limit=1)
        occupancy = min(100, round(len({o.get("table_id") for o in active if o.get("table_id")}) / 10 * 100))
        status = "Peak flow" if wait >= 22 or len(active) >= 6 else "Balanced" if active else "Calm"
        return {
            "status": status,
            "active_orders": len(active),
            "active_items": active_items,
            "predicted_wait": wait,
            "occupancy": occupancy,
            "trending": top[0]["name"] if top else (menu[0]["name"] if menu else "Chef special"),
            "model_version": MODEL_VERSION,
        }

    def analytics(self, menu: list[dict], orders: list[dict]) -> dict:
        today = dt.datetime.now().strftime("%Y-%m-%d")
        today_orders = [order for order in orders if order.get("date") == today]
        completed = [order for order in orders if order.get("status") == "Completed"]

        revenue = sum(self._order_total(order) for order in completed)
        today_revenue = sum(
        self._order_total(order)
        for order in today_orders
        if order.get("status") == "Completed"
    )

        active = [order for order in orders if order.get("status") in ACTIVE_STATUSES]

        hour_counts = Counter()
        for order in orders:
            if order.get("time") and ":" in order["time"]:
                hour_counts[int(order["time"].split(":")[0])] += 1

        if menu:
            waits = []

            for table_id in range(1, 6):
                sample_items = menu[: max(1, min(3, len(menu)))]
                wait = self.predict_wait_time(sample_items, table_id, orders, menu)
                waits.append(wait)

            avg_wait = int(sum(waits) / len(waits))
        else:
            avg_wait = 0

        return {
            "total_orders": len(orders),
            "today_orders": len(today_orders),
            "total_revenue": revenue,
            "today_revenue": today_revenue,
            "active_orders": len(active),
            "active_tables": sorted({order.get("table_id") for order in active if order.get("table_id")}),

            "avg_wait_time": avg_wait,

            "top_dishes": self._top_dishes(orders, limit=8),
            "hour_counts": dict(hour_counts),
            "ml_status": self.status(),
            "insights": self._insights(menu, orders, avg_wait),
        }

    def status(self) -> dict:
        meta = self._read_json(self.models_dir / "model_meta.json", {})
        return {
            "ready": bool(meta),
            "version": meta.get("version", MODEL_VERSION),
            "trained_at": meta.get("trained_at"),
            "models": meta.get("models", {}),
        }

    def model_card(self, key: str) -> dict:
        return self.status().get("models", {}).get(key, {})

    def extract_budget(self, text: str) -> int | None:
        text = text or ""
        matches = [int(match.group(1)) for match in RUPEE_RE.finditer(text)]
        if not matches:
            return None
        plausible = [value for value in matches if 50 <= value <= 5000]
        return min(plausible) if plausible else None

    def _train_recommendation(self, menu: list[dict]) -> dict:
        menu_docs = [self._dish_text(item) for item in menu]
        training_docs = self._recommendation_training_docs(menu)
        if not menu_docs:
            menu_docs = ["empty menu"]
        if not training_docs:
            training_docs = menu_docs
        vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, stop_words="english")
        vectorizer.fit(training_docs)
        matrix = vectorizer.transform(menu_docs)
        neighbors = NearestNeighbors(metric="cosine", algorithm="brute")
        neighbors.fit(matrix)
        artifact = {
            "vectorizer": vectorizer,
            "neighbors": neighbors,
            "matrix": matrix,
            "menu_ids": [item.get("id", idx) for idx, item in enumerate(menu)],
            "version": MODEL_VERSION,
        }
        joblib.dump(artifact, self.models_dir / "recommendation.joblib")
        return {
            "card": {
                "type": "TF-IDF + NearestNeighbors",
                "trained_rows": len(training_docs),
                "menu_vectors": len(menu_docs),
            }
        }

    def _recommendation_training_docs(self, menu: list[dict]) -> list[str]:
        docs = []
        intent_templates = [
            "guest wants {tags} {category} {name} under budget price {price_bucket}",
            "recommend {name} for {tags} craving in {category}",
            "customer preference {tags} meal with description {description}",
            "best {category} option for table dining {name} {tags}",
            "ai assistant query {tags} food similar to {name} price {price_bucket}",
        ]
        contextual_queries = [
            "spicy vegetarian starter under 300",
            "healthy high protein main course",
            "premium dinner signature dish",
            "light nut free snack",
            "sweet dessert after dinner",
            "popular filling comfort food",
            "mild vegetarian option",
            "non vegetarian chef special",
            "budget friendly quick bite",
            "rich creamy pasta",
        ]

        for item in menu:
            base = {
                "name": item.get("name", ""),
                "category": item.get("category", ""),
                "tags": " ".join(item.get("tags", [])),
                "description": item.get("description", ""),
                "price_bucket": self._price_bucket(item.get("price", 0)),
            }
            docs.append(self._dish_text(item))
            docs.extend(template.format(**base).lower() for template in intent_templates)

        for query in contextual_queries:
            docs.append(query)

        return docs

    def _train_intent(self) -> dict:
        examples = [
            # Greeting
            ("hi hello hey", "greeting"),
            ("good evening", "greeting"),

            # Recommendation (MOST IMPORTANT)
            ("what's popular tonight", "recommendation"),
            ("suggest something good", "recommendation"),
            ("what should i eat", "recommendation"),
            ("best dishes", "recommendation"),
            ("trending food", "recommendation"),

            # Diet
            ("vegetarian options", "diet"),
            ("veg food", "diet"),
            ("healthy food", "diet"),
            ("low calorie meal", "diet"),
            ("no meat dishes", "diet"),

            # Wait time
            ("how long is the wait", "wait_time"),
            ("what is the wait time", "wait_time"),
            ("how much time for order", "wait_time"),

            # Order
            ("i want to order", "order"),
            ("add this to cart", "order"),
            ("place order", "order"),
        ]
        train_x, train_y = [], []
        for text, label in examples:
            phrases = text.split()
            train_x.append(text)
            train_y.append(label)
            for word in phrases:
                train_x.append(word)
                train_y.append(label)
        pipeline = Pipeline(
            [
                ("tfidf", TfidfVectorizer(ngram_range=(1, 2))),
                ("clf", LogisticRegression(max_iter=500)),
            ]
        )
        pipeline.fit(train_x, train_y)
        joblib.dump({"pipeline": pipeline, "version": MODEL_VERSION}, self.models_dir / "intent.joblib")
        return {"card": {"type": "TF-IDF + LogisticRegression", "trained_rows": len(train_x)}}

    def _train_wait_time(self, menu: list[dict], orders: list[dict]) -> dict:
        rows = self._wait_training_rows(menu, orders)
        frame = pd.DataFrame(rows)
        y = frame.pop("wait_minutes")
        numeric = ["hour", "day_of_week", "active_orders", "active_items", "item_count", "total_amount", "table_id"]
        categorical = ["primary_category", "is_weekend", "is_peak"]
        preprocessor = ColumnTransformer(
            [
                ("num", StandardScaler(), numeric),
                ("cat", OneHotEncoder(handle_unknown="ignore"), categorical),
            ]
        )
        pipeline = Pipeline(
            [
                ("prep", preprocessor),
                ("model", RandomForestRegressor(n_estimators=220, random_state=42, min_samples_leaf=3)),
            ]
        )
        pipeline.fit(frame, y)
        joblib.dump(
            {
                "pipeline": pipeline,
                "features": numeric + categorical,
                "version": MODEL_VERSION,
                "training_rows": len(rows),
            },
            self.models_dir / "wait_time.joblib",
        )
        return {"card": {"type": "RandomForestRegressor", "trained_rows": len(rows)}}

    def _wait_training_rows(self, menu: list[dict], orders: list[dict]) -> list[dict]:
        rng = np.random.default_rng(42)
        categories = sorted({item.get("category", "mains") for item in menu}) or ["starters", "mains", "desserts"]
        rows = []

        for day in range(70):
            day_of_week = day % 7
            for hour in range(10, 24):
                peak = int(hour in {13, 14, 19, 20, 21})
                weekend = int(day_of_week in {5, 6})
                base_load = 1 + peak * 4 + weekend * 2
                for _ in range(5):
                    active_orders = int(max(0, rng.poisson(base_load)))
                    item_count = int(rng.integers(1, 6))
                    category = str(rng.choice(categories))
                    avg_price = float(np.mean([item.get("price", 220) for item in menu if item.get("category") == category] or [220]))
                    total_amount = int(avg_price * item_count * rng.uniform(0.82, 1.2))
                    active_items = active_orders * int(rng.integers(1, 4))
                    complexity = {"starters": 2.5, "mains": 6.5, "desserts": 3.5}.get(category, 4.5)
                    wait = (
                        5.5
                        + item_count * 1.5
                        + active_orders * 1.5
                        + active_items * 0.45
                        + complexity
                        + peak * 4.2
                        + weekend * 2.4
                        + rng.normal(0, 2.2)
                    )
                    rows.append(
                        {
                            "hour": hour,
                            "day_of_week": day_of_week,
                            "active_orders": active_orders,
                            "active_items": active_items,
                            "item_count": item_count,
                            "total_amount": total_amount,
                            "table_id": int(rng.integers(1, 11)),
                            "primary_category": category,
                            "is_weekend": str(bool(weekend)),
                            "is_peak": str(bool(peak)),
                            "wait_minutes": max(5, round(wait, 1)),
                        }
                    )

        for order in orders:
            if not order.get("eta"):
                continue
            feature = self._wait_features(order.get("items") or [order], order.get("table_id") or 5, orders, menu)
            feature["wait_minutes"] = int(order.get("eta"))
            rows.append(feature)
        return rows

    def _wait_features(self, items: list[dict], table_id: int, orders: list[dict], menu: list[dict]) -> dict:
        now = dt.datetime.now()
        active = [order for order in orders if order.get("status") in ACTIVE_STATUSES]
        active_items = sum(len(order.get("items") or [order]) for order in active)
        item_count = max(1, len(items))
        total = sum(int(item.get("price", 0)) for item in items)
        menu_by_name = {self._item_name(item).lower(): item for item in menu}
        first = items[0] if items else {}
        name = (first.get("item") or first.get("name") or "").lower()
        category = first.get("category") or menu_by_name.get(name, {}).get("category") or "mains"
        return {
            "hour": now.hour,
            "day_of_week": now.weekday(),
            "active_orders": len(active),
            "active_items": active_items,
            "item_count": item_count,
            "total_amount": total,
            "table_id": int(table_id),
            "primary_category": category,
            "is_weekend": str(now.weekday() in {5, 6}),
            "is_peak": str(now.hour in {13, 14, 19, 20, 21}),
        }

    def _predict_intent(self, message: str) -> str:
        model = self._load("intent.joblib")
        message = message.lower().strip()   # ADD THIS
        if not message:
            return "recommendation"
        return str(model["pipeline"].predict([message])[0])

    def _dish_text(self, item: dict) -> str:
        return " ".join(
            [
                str(item.get("name", "")),
                str(item.get("category", "")),
                " ".join(item.get("tags", [])),
                str(item.get("description", "")),
                f"price_{self._price_bucket(item.get('price', 0))}",
            ]
        ).lower()

    def _enrich_query(self, query: str, table_id: int | None) -> str:
        hour = dt.datetime.now().hour
        period = "lunch" if 11 <= hour < 16 else "dinner" if 16 <= hour < 23 else "snack"
        return f"{query or 'popular chef recommended'} {period} table {table_id or ''}".lower()

    def _price_bucket(self, price: int) -> str:
        if price <= 180:
            return "budget"
        if price <= 320:
            return "mid"
        return "premium"

    def _price_fit(self, price: int, budget: int | None) -> float:
        if not budget:
            return 0.55
        if price <= budget:
            return min(1.0, 0.65 + (budget - price) / max(budget, 1) * 0.35)
        return 0.0

    def _popularity_scores(self, orders: list[dict]) -> dict[str, float]:
        counts = Counter()
        for order in orders:
            for item in order.get("items") or []:
                name = item.get("item") or item.get("name")
                if name:
                    counts[name] += 1
            if order.get("item"):
                counts[order["item"]] += 1
        if not counts:
            return {}
        max_count = max(counts.values())
        return {name: count / max_count for name, count in counts.items()}

    def _top_dishes(self, orders: list[dict], limit: int) -> list[dict]:
        counts = Counter()
        revenue = defaultdict(int)
        for order in orders:
            for item in order.get("items") or []:
                name = item.get("item") or item.get("name")
                if name:
                    counts[name] += 1
                    revenue[name] += int(item.get("price", 0))
            if order.get("item"):
                counts[order["item"]] += 1
        return [
            {"name": name, "orders": count, "revenue": revenue[name]}
            for name, count in counts.most_common(limit)
        ]

    def _order_total(self, order: dict) -> int:
        return sum(int(item.get("price", 0)) for item in order.get("items") or [])

    def _item_name(self, item: dict) -> str:
        return item.get("item") or item.get("name") or "Item"

    def _reason_for_match(self, query: str, item: dict, score: float) -> str:
        tags = item.get("tags", [])
        query_lower = (query or "").lower()
        matched_tags = [tag for tag in tags if tag.lower() in query_lower]
        if matched_tags:
            return f"Matches {', '.join(matched_tags[:2])} preference"
        if score > 0.55:
            return "Strong semantic menu match"
        if "popular" in tags:
            return "Boosted by historical popularity"
        return "Closest learned menu match"

    def _insights(self, menu: list[dict], orders: list[dict], wait: int) -> list[str]:
        top = self._top_dishes(orders, 1)
        insights = []
        if top:
            insights.append(f"{top[0]['name']} is leading demand from historical order data.")
        if wait >= 22:
            insights.append("Wait model detects pressure building in the kitchen queue.")
        else:
            insights.append("Wait model indicates the kitchen can accept more orders comfortably.")
        if menu:
            rec = self.recommend("premium popular dinner", menu, orders, limit=1)
            if rec:
                insights.append(f"Recommendation model is currently surfacing {rec[0]['name']} for premium dinner intent.")
        return insights

    def _load(self, filename: str):
        if filename not in self._cache:
            self._cache[filename] = joblib.load(self.models_dir / filename)
        return self._cache[filename]

    def _read_json(self, path: Path, default):
        if not path.exists():
            return default
        try:
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except json.JSONDecodeError:
            return default

    def _write_json(self, path: Path, data) -> None:
        with path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2)

