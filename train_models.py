from __future__ import annotations

import json
from pathlib import Path

from ai_engine import RestaurantAI


BASE_DIR = Path(__file__).resolve().parent


def load_json(name: str, default):
    path = BASE_DIR / name
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def main():
    menu = load_json("menu.json", [])
    orders = load_json("orders.json", [])
    ai = RestaurantAI(BASE_DIR)
    meta = ai.train(menu, orders)
    print("Training complete")
    print(f"Version: {meta['version']}")
    print(f"Trained at: {meta['trained_at']}")
    for name, card in meta["models"].items():
        print(f"- {name}: {card['type']} on {card['trained_rows']} rows")


if __name__ == "__main__":
    main()
