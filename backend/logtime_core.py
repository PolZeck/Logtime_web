
import os
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import calendar
import holidays 

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


def get_logtime_data(login):
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    all_sessions = []
    page = 1

    while True:
        url = f"https://api.intra.42.fr/v2/users/{login}/locations?page={page}&per_page=100"
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


def calculate_dynamic_weekly_goal(now):
    WEEKLY_GOAL_PER_DAY_SEC = 7 * 3600
    fr_holidays = holidays.France(years=now.year)

    # Lundi de la semaine OU début du mois si on a commencé un nouveau mois cette semaine
    start_of_week = max(
        (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0),
        now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    )

    # Dimanche de la semaine actuelle
    end_of_week = start_of_week + timedelta(days=6)

    working_days = 0
    current = start_of_week.date()
    while current <= end_of_week.date():
        if current.weekday() < 5 and current not in fr_holidays:
            working_days += 1
        current += timedelta(days=1)

    return working_days * WEEKLY_GOAL_PER_DAY_SEC

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
        rounded_minutes = int(daily_seconds // 60)
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
            minutes = int(seconds / 60)
            total_seconds += minutes * 60
        else:
            total_seconds += seconds

    return total_seconds


# --- FORMATTAGE TEMPS ---
def format_time(seconds):
    total_minutes = seconds / 60
    rounded_minutes = int(total_minutes)  # arrondi à la minute la plus proche
    hours = rounded_minutes // 60
    minutes = rounded_minutes % 60
    return f"{hours}h {minutes}min"


# --- CALCUL DES OBJECTIFS ---
def calculate_remaining_times(login, now, logtime_week_sec, logtime_month_sec):
    from holidays import France
    fr_holidays = France(years=now.year)

    # 📅 Semaine commençant au lundi, mais pas avant le début du mois
    start_of_week = max(
        (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0),
        now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    )
    end_of_week = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    # 🔍 Jours ouvrés de la semaine dans le mois courant
    working_days = []
    current_day = start_of_week.date()
    while current_day <= end_of_week.date():
        if (current_day.month == now.month and
            current_day.weekday() < 5 and
            current_day not in fr_holidays):
            working_days.append(current_day)
        current_day += timedelta(days=1)

    # 🎯 Objectif hebdo dynamique
    WEEKLY_GOAL_SEC = len(working_days) * 7 * 3600

    # ⏱️ Logtime réellement fait sur ces jours-là
    sessions = get_logtime_data(login)
    week_logtime_filtered = 0
    for day in working_days:
        start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        week_logtime_filtered += calculate_logtime(sessions, start, end, round_daily=True)

    # 🎯 Objectif mensuel (inchangé)
    total_days = calendar.monthrange(now.year, now.month)[1]
    total_working_days = sum(
        1 for day in range(1, total_days + 1)
        if datetime(now.year, now.month, day).weekday() < 5
        and datetime(now.year, now.month, day).date() not in fr_holidays
    )
    MONTHLY_GOAL_SEC = total_working_days * 7 * 3600 + 5 * 60

    # ⏳ Restes
    remaining_week_sec = max(0, WEEKLY_GOAL_SEC - week_logtime_filtered)
    remaining_month_sec = max(0, MONTHLY_GOAL_SEC - logtime_month_sec)

    def fmt(sec):
        h, m = divmod(int(sec) // 60, 60)
        return f"{h}h {m}min"

    return fmt(remaining_week_sec), fmt(remaining_month_sec), MONTHLY_GOAL_SEC, WEEKLY_GOAL_SEC

# --- RAPPORT COMPLET ---
def get_logtime_report(login):
    sessions = get_logtime_data(login)
    now = datetime.now(timezone.utc)

    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_today = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    start_of_week = max(
        (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0),
        now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    )
    end_of_week = end_of_today

    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end_of_month = end_of_today

    from holidays import France
    fr_holidays = France(years=now.year)

    working_days_this_week = []
    current_day = start_of_week.date()
    while current_day <= end_of_week.date():
        if (current_day.month == now.month and
            current_day.weekday() < 5 and
            current_day not in fr_holidays):
            working_days_this_week.append(current_day)
        current_day += timedelta(days=1)

    logtime_week = 0
    for day in working_days_this_week:
        start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        logtime_week += calculate_logtime(sessions, start, end, now, round_daily=True)

    logtime_today = calculate_logtime(sessions, start_of_today, end_of_today, now, round_daily=True)
    logtime_month_raw = calculate_logtime(sessions, start_of_month, end_of_month, now, round_daily=True)

    remaining_week, remaining_month, monthly_goal_sec, weekly_goal_sec = calculate_remaining_times(
        login, now, logtime_week, logtime_month_raw
    )

    monthly_goal_hours = int(monthly_goal_sec // 3600)
    weekly_goal_hours = int(weekly_goal_sec // 3600)

    logtime_month_display = max(0, logtime_month_raw)

    return {
        "today": format_time(logtime_today),
        "week": format_time(logtime_week),
        "month": format_time(logtime_month_display),
        "week_raw": logtime_week,
        "month_raw": logtime_month_display,
        "now": now,
        "remaining_month": remaining_month,
        "remaining_week": remaining_week,
        "monthly_goal_hours": monthly_goal_hours,
        "weekly_goal_hours": weekly_goal_hours
    }

def get_monthly_logtime_breakdown(login):
    sessions = get_logtime_data(login)
    now = datetime.now(timezone.utc)
    year, month = now.year, now.month

    days_in_month = calendar.monthrange(year, month)[1]
    breakdown = {}

    for day in range(1, days_in_month + 1):
        date = datetime(year, month, day, tzinfo=timezone.utc)
        next_day = date + timedelta(days=1)
        seconds = calculate_logtime(sessions, date, next_day, now, round_daily=True)
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        breakdown[day] = f"{hours}h {minutes}min" if seconds else ""
    
    return breakdown

# --- Entrée dynamique ---
def get_logtime_report_for(login):
    return get_logtime_report(login)

