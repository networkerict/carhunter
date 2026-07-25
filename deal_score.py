"""
AutoHunter v3.0-dev
Deal scoring engine
"""


def calculate_deal_score(car):

    score = 0


    # Hoge auto score
    if car.final_score >= 85:
        score += 40

    elif car.final_score >= 80:
        score += 25


    # Grote prijsdaling
    if car.price_drop:

        if car.price_drop >= 2000:
            score += 20

        elif car.price_drop >= 1000:
            score += 10


    # Veel opties
    if car.options_score >= 80:
        score += 10


    # Nieuwe auto
    if car.status == "new":
        score += 5


    return score
