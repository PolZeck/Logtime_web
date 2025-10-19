from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import requests

app = Flask(__name__)

# === CORS configuration ===
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=False)

@app.after_request
def add_cors_headers(resp):
	resp.headers["Access-Control-Allow-Origin"] = "*"
	resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
	resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
	return resp


# === Utility function for safe JSON parsing ===
def safe_json(res):
	try:
		return res.json()
	except Exception:
		snippet = (res.text or "")[:300]
		raise RuntimeError(f"Réponse non-JSON ({res.status_code}). Corps: {snippet}")


# === Get OAuth token from 42 API ===
def get_access_token():
	cid = os.getenv("CLIENT_ID")
	sec = os.getenv("CLIENT_SECRET")
	if not cid or not sec:
		raise RuntimeError("CLIENT_ID/CLIENT_SECRET manquants dans l'environnement Render.")
	
	url = "https://api.intra.42.fr/oauth/token"
	payload = {
		"grant_type": "client_credentials",
		"client_id": cid,
		"client_secret": sec
	}

	r = requests.post(url, data=payload, timeout=15)
	if not r.ok:
		raise RuntimeError(f"Echec OAuth {r.status_code}: {(r.text or '')[:200]}")
	
	data = safe_json(r)
	return data["access_token"]


# === Main route: /logtime ===
@app.route("/logtime", methods=["GET", "OPTIONS"])
def logtime():
	if request.method == "OPTIONS":
		return ("", 204)  # Répond au pré-vol CORS

	login = request.args.get("login", "").strip()
	if not login:
		return jsonify(error="login manquant"), 400

	try:
		token = get_access_token()
		api_url = f"https://api.intra.42.fr/v2/users/{login}/locations?per_page=100"
		r = requests.get(
			api_url,
			headers={"Authorization": f"Bearer {token}"},
			timeout=20
		)

		if not r.ok:
			return jsonify(error=f"API 42 {r.status_code}", body=(r.text or "")[:300]), 502

		data = safe_json(r)
		return jsonify(result=data)

	except Exception as e:
		print("ERREUR /logtime:", repr(e))
		return jsonify(error=str(e)), 500


# === Flask entrypoint for Render ===
if __name__ == "__main__":
	app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
