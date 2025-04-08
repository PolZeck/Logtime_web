from flask import Flask, request, jsonify
from flask_cors import CORS
from logtime_core import get_logtime_report_for, calculate_remaining_times, get_monthly_logtime_breakdown
import os

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

@app.route("/logtime")
def logtime():
    login = request.args.get("login")
    if not login:
        return jsonify({"error": "Login manquant"}), 400
    print(f"Requête reçue pour le login : {login}")
    try:
        report = get_logtime_report_for(login)
        
        # 🔁 Corrigé ici : ajout de login en premier argument
        remaining_week, remaining_month, monthly_goal_sec, weekly_goal_sec = calculate_remaining_times(
            login, report["now"], report["week_raw"], report["month_raw"]
        )

        monthly_goal_hours = int(monthly_goal_sec // 3600)
        calendar_data = get_monthly_logtime_breakdown(login)


        return jsonify({
            "today": report["today"],
            "week": report["week"],
            "month": report["month"],
            "remaining_week": remaining_week,  # ⬅️ corrigé
            "remaining_month": remaining_month,
            "month_raw": report["month_raw"],
            "monthly_goal_hours": monthly_goal_hours,
            "weekly_goal_hours": int(weekly_goal_sec // 3600),
            "calendar": calendar_data  # 👈 on ajoute le calendrier ici
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
