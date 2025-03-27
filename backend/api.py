from flask import Flask, request, jsonify
from logtime_core import get_logtime_report_for, calculate_remaining_times

app = Flask(__name__)

@app.route("/logtime")
def logtime():
    login = request.args.get("login")
    if not login:
        return jsonify({"error": "Login manquant"}), 400
    try:
        report = get_logtime_report_for(login)
        remaining_week, remaining_month = calculate_remaining_times(
            report["now"], report["week_raw"], report["month_raw"]
        )
        return jsonify({
            "today": report["today"],
            "week": report["week"],
            "month": report["month"],
            "remaining_week": remaining_week,
            "remaining_month": remaining_month
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
