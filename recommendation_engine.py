#!/usr/bin/env python3

"""
AutoHunter v2.9
Recommendation engine
"""

import comparison_intelligence
import value_intelligence
import option_intelligence



def generate_recommendation(cars):

    comparison = (
        comparison_intelligence.analyze_comparison(
            cars
        )
    )


    value = (
        value_intelligence.analyze_value(
            cars
        )
    )


    winner = comparison["winner"]


    value_choice = None

    if value:

        value_choice = (
            value[0]["car"]
        )


    premium_advantages = []


    if winner:

        premium_advantages = (
            option_intelligence.get_weighted_advantages(
                winner,
                cars
            )
        )


    price_difference = 0

    score_difference = 0


    if winner and value_choice:

        price_difference = (
            winner.price
            -
            value_choice.price
        )


        score_difference = (
            winner.final_score
            -
            value_choice.final_score
        )


    headline = ""

    if winner and value_choice:

        if winner.id == value_choice.id:

            headline = (
                "🏆 Beste keuze én beste waarde"
            )

        else:

            headline = (
                "🏆 Beste keuze met alternatief"
            )


    reasons = []


    if winner:

        reasons.append(
            f"Hoogste totaalscore ({winner.final_score})"
        )


    for item in premium_advantages[:5]:

        reasons.append(
            item["option"]
        )


    recommendation = {

        "winner": winner,

        "value_choice": value_choice,

        "winner_reasons":
            comparison["reasons"],

        "winner_warnings":
            comparison["warnings"],

        "premium_advantages":
            premium_advantages,

        "price_difference":
            price_difference,

        "score_difference":
            score_difference,

        "value_ratio":
            value[0]["ratio"]
            if value
            else 0,

        "headline":
            headline,

        "recommendation_reasons":
            reasons,

        "summary":
            ""

    }


    if winner and value_choice:

        if winner.id == value_choice.id:

            recommendation["summary"] = (
                f"{winner.title} combineert de hoogste "
                f"score ({winner.final_score}) met de beste "
                "prijs/kwaliteit verhouding."
            )

        else:

            recommendation["summary"] = (
                f"{winner.title} is de beste keuze. "
                f"{value_choice.title} is het slimste "
                f"waarde alternatief (€{abs(price_difference)} verschil)."
            )


    return recommendation
