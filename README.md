# LUME - AI-Powered Restaurant Intelligence

Flask + HTML/CSS/Vanilla JS restaurant ordering system for the AIML project.

## What is ML-backed

- `models/recommendation.joblib`: TF-IDF + nearest-neighbor content recommender trained on augmented menu/query examples.
- `models/intent.joblib`: TF-IDF + Logistic Regression assistant intent classifier.
- `models/wait_time.joblib`: Random Forest wait-time regressor trained from generated restaurant operations samples plus historical order ETAs from `orders.json`.

## UI

The frontend is converted from the Google Stitch LuminaCuisine dark UI direction:

- Premium light glassmorphism, white cards, indigo accents, and icon-only chrome.
- Landing bento hero, AI menu grid, assistant chat, admin analytics, and wait-time status views.
- Plain Flask templates, CSS3, and vanilla JavaScript connected to the ML backend.

## Run

```bash
pip install -r requirements.txt
python3 train_models.py
python3 app.py
```

Open:

- Guest landing: `http://127.0.0.1:5000/`
- QR menu: `http://127.0.0.1:5000/table/5`
- Assistant: `http://127.0.0.1:5000/assistant/5`
- Dashboard: `http://127.0.0.1:5000/dashboard`

If the `models` folder is missing, the Flask app trains models automatically on startup/request.
