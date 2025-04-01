
import os
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import calendar

load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
USER_LOGIN = "pledieu"  # sera modifié dynamiquement par get_logtime_report_for()

# --- API 42 ---
def get_access_token():
    url = "https://api.intra.42.fr/oauth/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    response = requests.post(url, data=data)
    return response.json().get("access_token")


def get_logtime_data():
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    all_sessions = []
    page = 1

    while True:
        url = f"https://api.intra.42.fr/v2/users/{USER_LOGIN}/locations?page={page}&per_page=100"
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print("Erreur API:", response.text)
            break

        page_data = response.json()
        if not page_data:
            break

        all_sessions.extend(page_data)
        page += 1

    return all_sessions

def calculate_daily_logtime(sessions, start_date, end_date, now=None):
    if now is None:
        now = datetime.now(timezone.utc)

    # Trie les sessions par début
    sessions = sorted(sessions, key=lambda s: s["begin_at"])
    daily_totals = {}

    for session in sessions:
        begin_at = datetime.strptime(session["begin_at"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        end_raw = session["end_at"]
        end_at = (
            datetime.strptime(end_raw, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
            if end_raw else now
        )

        # Ignore hors période
        if begin_at >= end_date or end_at <= start_date:
            continue

        # Tronque aux limites
        begin_at = max(begin_at, start_date)
        end_at = min(end_at, end_date)

        day_key = begin_at.date()
        if day_key not in daily_totals:
            daily_totals[day_key] = []

        daily_totals[day_key].append((begin_at, end_at))

    total_seconds = 0

    for intervals in daily_totals.values():
        # Fusion des intervalles de la journée
        intervals.sort()
        merged = []

        for begin, end in intervals:
            if not merged:
                merged.append((begin, end))
            else:
                last_begin, last_end = merged[-1]
                if begin <= last_end:
                    merged[-1] = (last_begin, max(last_end, end))
                else:
                    merged.append((begin, end))

        # Calcul du total de la journée
        daily_seconds = sum((end - start).total_seconds() for start, end in merged)

        # ✅ Arrondi à la minute la plus proche (journée entière)
        rounded_minutes = int(daily_seconds / 60 + 0.5)
        total_seconds += rounded_minutes * 60

    return total_seconds


# --- CALCUL DU TEMPS EN FUSIONNANT LES SESSIONS ---
def calculate_logtime(sessions, start_date, end_date, now=None, round_daily=False):
    if now is None:
        now = datetime.now(timezone.utc)

    sessions = sorted(sessions, key=lambda s: s["begin_at"])
    grouped_by_day = {}

    for session in sessions:
        begin_at = datetime.strptime(session["begin_at"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        end_raw = session["end_at"]
        end_at = (
            datetime.strptime(end_raw, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
            if end_raw else now
        )

        if begin_at >= end_date or end_at <= start_date:
            continue

        begin_at = max(begin_at, start_date)
        end_at = min(end_at, end_date)

        day = begin_at.date() if round_daily else None
        key = day if round_daily else 0

        if key not in grouped_by_day:
            grouped_by_day[key] = []

        grouped_by_day[key].append((begin_at, end_at))

    total_seconds = 0

    for intervals in grouped_by_day.values():
        intervals.sort()
        merged = []

        for begin, end in intervals:
            if not merged:
                merged.append((begin, end))
            else:
                last_begin, last_end = merged[-1]
                if begin <= last_end:
                    merged[-1] = (last_begin, max(last_end, end))
                else:
                    merged.append((begin, end))

        seconds = sum((end - start).total_seconds() for start, end in merged)

        if round_daily:
            minutes = int(seconds / 60 + 0.5)
            total_seconds += minutes * 60
        else:
            total_seconds += seconds

    return total_seconds


# --- FORMATTAGE TEMPS ---
def format_time(seconds):
    total_minutes = seconds / 60
    rounded_minutes = int(total_minutes + 0.5)  # arrondi à la minute la plus proche
    hours = rounded_minutes // 60
    minutes = rounded_minutes % 60
    return f"{hours}h {minutes}min"


# --- CALCUL DES OBJECTIFS ---
def calculate_remaining_times(now, logtime_week_sec, logtime_month_sec):
    WEEKLY_GOAL_SEC = 35 * 3600
    total_days = calendar.monthrange(now.year, now.month)[1]
    total_working_days = sum(
        1 for day in range(1, total_days + 1)
        if datetime(now.year, now.month, day).weekday() < 5
    )
    MONTHLY_GOAL_SEC = total_working_days * 7 * 3600

    remaining_week_sec = max(0, WEEKLY_GOAL_SEC - logtime_week_sec)
    remaining_month_sec = max(0, MONTHLY_GOAL_SEC - logtime_month_sec)

    def fmt(sec):
        h, m = divmod(int(sec) // 60, 60)
        return f"{h}h {m}min"

    return fmt(remaining_week_sec), fmt(remaining_month_sec)

# --- RAPPORT COMPLET ---
def get_logtime_report():
    sessions = get_logtime_data()
    now = datetime.now(timezone.utc)

    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_today = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    start_of_week = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_week = end_of_today

    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end_of_month = end_of_today

    # Utilisation cohérente de l'arrondi quotidien
    logtime_today = calculate_logtime(sessions, start_of_today, end_of_today, now, round_daily=True)
    logtime_week = calculate_logtime(sessions, start_of_week, end_of_week, now, round_daily=True)
    logtime_month_raw = calculate_logtime(sessions, start_of_month, end_of_month, now, round_daily=True)

    # ⏳ Affichage mois avec -10min
    logtime_month_display = max(0, logtime_month_raw - 5 * 60)

    return {
        "today": format_time(logtime_today),
        "week": format_time(logtime_week),
        "month": format_time(logtime_month_display),
        "week_raw": logtime_week,
        "month_raw": logtime_month_display,
        "now": now
    }

# --- Entrée dynamique ---
def get_logtime_report_for(login):
    global USER_LOGIN
    USER_LOGIN = login
    return get_logtime_report()
