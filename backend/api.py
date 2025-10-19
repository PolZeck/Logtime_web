from flask import Flask, request, jsonify
from flask_cors import CORS
from logtime_core import get_logtime_report_for, calculate_remaining_times, get_monthly_logtime_breakdown
import os

# api.py (ou le module de ta route Flask)
from flask import Flask, jsonify, request
import os, requests

app = Flask(__name__)

def safe_json(res):
    try:
        return res.json()
    except Exception:
        snippet = (res.text or "")[:300]
        raise RuntimeError(f"Réponse non-JSON ({res.status_code}). Corps: {snippet}")

def get_access_token():
    cid = os.getenv("CLIENT_ID")
    sec = os.getenv("CLIENT_SECRET")
    if not cid or not sec:
        raise RuntimeError("CLIENT_ID/CLIENT_SECRET manquants dans l'environnement Render.")
    r = requests.post(
        "https://api.intra.42.fr/oauth/token",
        data={"grant_type":"client_credentials","client_id":cid,"client_secret":sec},
        timeout=15
    )
    if not r.ok:
        raise RuntimeError(f"Echec OAuth {r.status_code}: {(r.text or '')[:200]}")
    return safe_json(r)["access_token"]

@app.get("/logtime")
def logtime():
    login = request.args.get("login","").strip()
    if not login:
        return jsonify(error="login manquant"), 400
    try:
        token = get_access_token()
        r = requests.get(
            f"https://api.intra.42.fr/v2/users/{login}/locations?per_page=100",
            headers={"Authorization": f"Bearer {token}"},
            timeout=20
        )
        if not r.ok:
            # on remonte l'erreur claire (401/403/404/429/5xx…)
            return jsonify(error=f"API 42 {r.status_code}", body=(r.text or "")[:300]), 502
        data = safe_json(r)
        # ... tes calculs ici ...
        return jsonify(result=data)  # temporaire pour valider le flux
    except Exception as e:
        # log côté serveur et message clair côté client
        print("ERREUR /logtime:", repr(e))
        return jsonify(error=str(e)), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
