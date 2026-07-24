"""
AutoHunter v2.9-dev
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



def send_pipeline_summary(stats):

    message = f"""
🚗 AutoHunter Pipeline

🔥 High score auto's: {stats.get('high_score_cars',0)}
💰 Prijsdalingen: {stats.get('price_drops',0)}
"""

    send_message(
        message.strip()
    )



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

