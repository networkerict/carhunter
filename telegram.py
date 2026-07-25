"""
AutoHunter v3.0-dev
Telegram notifications
"""

import os
import requests
from dotenv import load_dotenv
import debug
import recommendation
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(
    BASE_DIR / ".env",
    override=True
)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_message(message):

    if not TOKEN or not CHAT_ID:
        debug.info(
            "Telegram configuration missing"
        )
        return False


    url = (
        f"https://api.telegram.org/"
        f"bot{TOKEN}/sendMessage"
    )


    data = {
        "chat_id": CHAT_ID,
        "text": message
    }


    try:

        response = requests.post(
            url,
            data=data,
            timeout=10
        )


        if response.ok:
            debug.info(
                "Telegram message sent"
            )
            return True


        debug.info(
            f"Telegram error: {response.text}"
        )

        return False


    except Exception as e:

        debug.info(
            f"Telegram exception: {e}"
        )

        return False



def build_pipeline_summary_message(run_stats=None, db_stats=None):

    run_stats = run_stats or {}
    db_stats = db_stats or {}

    lines = [
        "🚗 AutoHunter Pipeline",
        "",
        f"✅ {run_stats.get('status', 'UNKNOWN')} ({run_stats.get('duration_seconds', 0)} sec)",
        "",
        f"📥 New cars: {run_stats.get('new_cars', 0)}",
        f"🚫 Not available anymore: {run_stats.get('not_available_anymore', 0)}",
        f"💰 Price drops: {run_stats.get('price_drops', 0)}",
        f"🔥 High score cars: {run_stats.get('high_score_cars', 0)}",
        f"📝 Descriptions updated: {run_stats.get('descriptions_updated', 0)}",
        f"⚙️ Options updated: {run_stats.get('options_updated', 0)}",
        f"🚨 Alerts sent: {run_stats.get('alerts_sent', 0)}",
        "",
        "📊 Database",
        f"🚗 Active cars: {db_stats.get('active_cars', 0)}",
        f"🚫 Not available anymore: {db_stats.get('not_available_anymore_total', 0)}",
    ]

    return "\n".join(lines).strip()


def send_pipeline_summary(run_stats=None, db_stats=None):

    message = build_pipeline_summary_message(
        run_stats,
        db_stats
    )

    return send_message(message)



def get_recommendation_text(car):

    reasons = recommendation.explain_car(
        car
    )

    if not reasons:
        return ""

    text = "🧠 Waarom interessant:\n\n"

    for reason in reasons:

        text += f"✓ {reason}\n"

    return text


def send_deal_alert(car):

    message = f"""
🔥 AutoHunter Deal gevonden!

🚗 {car.title}

⭐ Auto score:
{car.final_score}

❤️ Personal score:
{car.personal_score}

🔥 Deal score:
{car.deal_score}


{get_recommendation_text(car)}

💰 Prijs:
€{car.price}

🎯 Opties:
{car.options_score}

📅 {car.year}
🚗 {car.km} km

{car.url}
"""

    send_message(
        message.strip()
    )

def send_watchlist_alert(car):

    message = f"""
❤️ Nieuwe Watchlist Match!

🚗 {car.title}

⭐ Personal Score :
{car.personal_score}

🏆 AutoHunter Score:
{car.final_score}

🔥 Deal Score:
{car.deal_score}


{get_recommendation_text(car)}

💰 €{car.price}

📅 {car.year}
🛣️ {car.km} km

🎯 Optiescore:
{car.options_score}

🔗 {car.url}
"""

    return send_message(
        message.strip()
    )


def send_today_report(cars):

    if not cars:

        return False


    message = f"""
🚗 AutoHunter Nieuwe auto's

Nieuwe auto's gevonden: {len(cars)}

"""

    for index, car in enumerate(cars, 1):

        message += (
            f"{index}. {car.title}\n"
            f"⭐ Score: {car.final_score}\n"
            f"💰 €{car.price}\n"
            f"📅 {car.year}\n"
            f"🛣️ {car.km} km\n\n"
        )


    return send_message(
        message.strip()
    )

