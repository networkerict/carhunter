from flask import Flask, render_template, redirect
import database
import debug
import data_quality
import orchestration

app = Flask(__name__)
app.jinja_env.globals['format_currency'] = lambda value: format_currency(value)


def format_currency(value):
    if value is None:
        return "—"
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return "—"
    try:
        return f"€{int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


@app.route("/")
def index():

    from flask import request


    cars = database.search_cars(

        max_price=request.args.get(
            "price",
            type=int
        ),

        min_year=request.args.get(
            "year",
            type=int
        ),

        max_km=request.args.get(
            "km",
            type=int
        ),

        min_score=request.args.get(
            "score",
            type=int
        ),

        search=request.args.get(
            "search"
        ),

        colors=request.args.getlist(
            "color"
        ),

        color_details=request.args.getlist(
            "color_detail"
        ),

        options=request.args.getlist("option")

    )


    active_filters = {}

    if request.args.get("price"):
        active_filters["Prijs"] = f"< €{request.args.get('price')}"

    if request.args.get("year"):
        active_filters["Bouwjaar"] = f"> {request.args.get('year')}"

    if request.args.get("km"):
        active_filters["KM"] = f"< {request.args.get('km')}"

    if request.args.get("score"):
        active_filters["Score"] = f"> {request.args.get('score')}"


    if request.args.getlist("color"):
        active_filters["Kleur"] = ", ".join(
            request.args.getlist("color")
        )

    if request.args.getlist("option"):
        active_filters["Opties"] = ", ".join(
            request.args.getlist("option")
        )


    return render_template(
        "index.html",
        cars=cars,
        active_filters=active_filters,
        filters=request.args,
        options=database.get_option_counts(),
        color_details=database.get_color_detail_counts()
    )


@app.route("/car/<int:id>")
def car_detail(id):

    car = database.get_car(id)

    return render_template(
        "car.html",
        car=car
    )

@app.route("/car/<int:id>/debug-score")
def debug_score_page(id):

    import scoring
    import options
    import premium


    car = database.get_car(id)

    if not car:
        return "Car not found", 404


    car_score, car_breakdown = scoring.calculate_car_score(
        car,
        explain=True
    )


    value_score, value_breakdown = scoring.calculate_value_score(
        car,
        explain=True
    )


    found, option_score, option_breakdown = options.analyze_options(
        car,
        explain=True
    )


    premium_score, premium_breakdown = premium.analyze_premium(
        car,
        explain=True
    )


    return render_template(
        "debug_score.html",
        car=car,
        car_score=car_score,
        car_breakdown=car_breakdown,
        value_score=value_score,
        value_breakdown=value_breakdown,
        options=found,
        options_score=option_score,
        option_breakdown=option_breakdown,
        premium_score=premium_score,
        premium_breakdown=premium_breakdown
    )


@app.route("/compare")
def compare():

    from flask import request
    import comparison

    ids = request.args.getlist("ids")

    cars = []

    for id in ids:

        car = database.get_car(
            int(id)
        )

        if car:
            cars.append(car)


    option_matrix = comparison.get_all_options(
        cars
    )

    import comparison_intelligence
    import recommendation_engine


    comparison_analysis = (
        comparison_intelligence.analyze_comparison(
            cars
        )
    )


    recommendation = (
        recommendation_engine.generate_recommendation(
            cars
        )
    )


    return render_template(
        "compare.html",
        cars=cars,
        option_matrix=option_matrix,
        comparison_analysis=comparison_analysis,
        recommendation=recommendation
    )


@app.route("/dashboard")
def dashboard():

    import dashboard_data

    data = dashboard_data.get_dashboard_data()

    return render_template(
        "dashboard.html",
        data=data
    )


@app.route("/data-quality")
def data_quality_dashboard():

    summary = data_quality.get_dashboard_summary()
    integrity = data_quality.run_integrity_checks()

    return render_template(
        "data_quality_dashboard.html",
        summary=summary,
        field_summary=summary["field_summary"],
        integrity=integrity,
    )


@app.route("/ranking")
def ranking():

    cars = database.get_ranking(10)

    return render_template(
        "ranking.html",
        cars=cars
    )

@app.route("/deals")
def deals():

    import debug_deal

    cars = database.get_deals()

    for car in cars:

        score, reasons = debug_deal.explain_deal(car)

        car.deal_reasons = reasons


    return render_template(
        "deals.html",
        cars=cars
    )

@app.route("/duplicates")
def duplicates_list():
    from flask import request
    import duplicate_detection as dd

    classification = request.args.get("classification") or None
    status = request.args.get("status") or None

    candidates = dd.get_duplicate_candidates(
        classification=classification,
        status=status,
    )
    summary = dd.get_review_summary()

    return render_template(
        "duplicates.html",
        candidates=candidates,
        summary=summary,
        filter_classification=classification,
        filter_status=status,
        view="list",
    )


@app.route("/duplicates/<int:candidate_id>")
def duplicate_detail(candidate_id):
    import duplicate_detection as dd

    candidate = dd.get_duplicate_candidate(candidate_id)
    if candidate is None:
        return "Candidate not found", 404

    summary = dd.get_review_summary()
    next_id = dd.get_next_open_candidate(after_id=candidate_id)

    return render_template(
        "duplicates.html",
        candidate=candidate,
        summary=summary,
        next_id=next_id,
        view="detail",
    )


@app.route("/duplicates/<int:candidate_id>/review", methods=["POST"])
def duplicate_review(candidate_id):
    from flask import request
    import duplicate_detection as dd

    status = request.form.get("status")
    comment = request.form.get("operator_comment", "").strip() or None

    allowed = {"CONFIRMED_SAME", "CONFIRMED_DIFFERENT", "UNSURE", "DISMISSED", "OPEN"}
    if status not in allowed:
        return "Invalid status", 400

    dd.update_duplicate_candidate_review(
        candidate_id,
        status=status,
        operator_comment=comment,
    )

    # Navigate to next OPEN candidate, or back to list
    next_id = dd.get_next_open_candidate(after_id=candidate_id)
    if next_id:
        return redirect(f"/duplicates/{next_id}")
    return redirect("/duplicates")


@app.route("/rescore")
def rescore():

    debug.info(
        "Web rescore gestart"
    )

    orchestration.run_pipeline(
        "rescore"
    )

    debug.info(
        "Web rescore afgerond"
    )

    return redirect("/ranking")


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5001,
        debug=False
    )
