"""Read-only local budget advice; monetary scenarios are calculated by Python."""

import json
from decimal import Decimal

from sqlalchemy import select

from .advisor_history import spending_history
from .advisor_prompts import system_instructions
from .budget import ActualWindow, ForecastInputs, forecast, shift_month
from .category_planning import category_averages
from .clock import local_today
from .local_model import chat_with_model
from .models import Category, Purchase, Settings
from .research import PublicResearchRequest, gather_research
from .savings import advisor_savings_projection


def forecast_comparison(db, month, inputs=None, categories=None):
    """Explain forecast changes without mixing in actuals or informational guides."""
    inputs = inputs or ForecastInputs(db)
    previous_month = shift_month(month, -1)
    previous, current = inputs.forecast(previous_month), inputs.forecast(month)
    categories = {
        c.id: c.name
        for c in (
            categories if categories is not None else db.scalars(select(Category)).all()
        )
    }
    schedules = {r.id: r for r in inputs.schedules}
    before = {line["id"]: line for line in previous["lines"]}
    after = {line["id"]: line for line in current["lines"]}
    changes = []
    for key in sorted(before.keys() | after.keys()):
        line = after.get(key) or before[key]
        old, new = (
            before.get(key, {}).get("amount", 0),
            after.get(key, {}).get("amount", 0),
        )
        if old == new:
            continue
        schedule = schedules.get(key)
        changes.append(
            {
                "name": line["name"],
                "kind": line["kind"],
                "category": categories.get(line["category_id"]),
                "source": "recurring" if schedule else "included_purchase",
                "frequency": schedule.frequency if schedule else None,
                "annual_distributed": schedule.distribute_annual
                if schedule and schedule.frequency == "annual"
                else None,
                "change": "added"
                if not old
                else "removed"
                if not new
                else "amount_changed",
                "previous_minor": old,
                "current_minor": new,
                "delta_minor": new - old,
                "remaining_impact_minor": new - old
                if line["kind"] == "receivable"
                else old - new,
            }
        )
    changes.sort(
        key=lambda row: (row["remaining_impact_minor"], row["name"].casefold())
    )

    def totals(value):
        return {
            key + "_minor": value[key] for key in ("income", "expenses", "remaining")
        } | {
            "income_recorded": any(
                line["kind"] == "receivable" for line in value["lines"]
            )
        }

    return {
        "previous_month": previous_month,
        "month": month,
        "previous": totals(previous),
        "current": totals(current),
        "income_change_minor": current["income"] - previous["income"],
        "expense_change_minor": current["expenses"] - previous["expenses"],
        "remaining_change_minor": current["remaining"] - previous["remaining"],
        "shortfall_minor": max(0, -current["remaining"]),
        "changes": changes,
        "current_expense_categories": [
            {
                "name": categories.get(cid, "Uncategorized"),
                "amount_minor": sum(
                    line["amount"]
                    for line in current["lines"]
                    if line["kind"] == "payable" and line["category_id"] == cid
                ),
            }
            for cid in sorted(
                {
                    line["category_id"]
                    for line in current["lines"]
                    if line["kind"] == "payable"
                },
                key=lambda cid: categories.get(cid, ""),
            )
        ],
    }


def budget_context(db, request):
    currency = db.get(Settings, 1).currency
    today = local_today()
    inputs = ForecastInputs(db)
    horizon = 24 if request.use_web else 12
    months = [shift_month(request.month, offset) for offset in range(horizon)]
    projections = []
    for month in months:
        f = forecast(db, month, inputs=inputs)
        projections.append(
            {
                "month": month,
                "income_minor": f["income"],
                "expenses_minor": f["expenses"],
                "remaining_minor": f["remaining"],
                "income_entries": sum(
                    line["kind"] == "receivable" for line in f["lines"]
                ),
            }
        )
    scenario = None
    purchase = db.get(Purchase, request.purchase_id) if request.purchase_id else None
    if purchase or request.scenario:
        item = purchase or request.scenario
        included = bool(purchase and purchase.included)
        baseline = forecast(db, item.month, inputs=inputs)
        after = baseline["remaining"] - (0 if included else item.amount)
        scenario = {
            "name": item.name,
            "month": item.month,
            "amount_minor": item.amount,
            "already_included": included,
            "baseline_remaining_minor": baseline["remaining"],
            "remaining_after_purchase_minor": after,
            "would_exceed_forecast": after < 0,
        }
    categories = db.scalars(select(Category).order_by(Category.name)).all()
    recent = []
    actuals = ActualWindow(db, shift_month(request.month, -2), request.month)
    for offset in (-2, -1, 0):
        month = shift_month(request.month, offset)
        values = actuals.actual(month)
        totals = actuals.totals.get(month, {})
        recent.append(
            {
                "month": month,
                "status": values["status"],
                "total_spending_minor": None
                if values["status"] == "missing"
                else values["expenses"],
                "categories": [
                    {"name": c.name, "spending_minor": totals[c.id]}
                    for c in categories
                    if totals.get(c.id)
                ],
            }
        )
    drafts = db.scalars(
        select(Purchase)
        .where(
            Purchase.included == False,
            Purchase.month >= months[0],
            Purchase.month <= months[-1],
        )
        .order_by(Purchase.month, Purchase.name)
    ).all()
    savings_projection = advisor_savings_projection(db, request, inputs=inputs)
    guide_end = shift_month(request.month, -1)
    guide_stats = (
        category_averages(db, guide_end, categories=categories)["categories"]
        if guide_end >= "1900-12"
        else []
    )
    return {
        "currency": currency,
        "minor_unit_digits": 0 if currency == "JPY" else 2,
        "selected_month": request.month,
        "current_date": today.isoformat(),
        "rules": {
            "months_are_independent": True,
            "carry_forward": False,
            "actual_spending_is_separate_from_forecast": True,
            "annual_expenses_follow_schedule_distribution": True,
            "category_guides_are_informational_not_expenses": True,
            "bank_balances_and_savings_are_unknown": savings_projection is None
            or not savings_projection["savings_known"],
            "draft_purchases_are_excluded_unless_selected_as_scenario": True,
        },
        "monthly_forecasts": projections,
        "recent_actuals": recent,
        "spending_history": spending_history(db, request.month, today, categories),
        "forecast_comparison": forecast_comparison(
            db, request.month, inputs=inputs, categories=categories
        ),
        "draft_purchases": [
            {"name": p.name, "month": p.month, "amount_minor": p.amount}
            for p in drafts[:20]
        ],
        "additional_drafts_omitted": max(0, len(drafts) - 20),
        "purchase_scenario": scenario,
        "planning_capacity": planning_capacity(
            db, request, today, scenario, inputs=inputs
        ),
        "savings_projection": savings_projection,
        "category_guides": [
            {
                "name": row["name"],
                "monthly_guide_minor": row["monthly_guide"],
                "recorded_average_minor": row["average"],
                "sample_count": row["sample_count"],
                "partial_month_count": row["partial_month_count"],
            }
            for row in guide_stats
        ],
    }


def planning_capacity(db, request, today, scenario, inputs=None):
    """Hypothetical earmarking of monthly surplus, never budget carry-forward."""
    inputs = inputs or ForecastInputs(db)
    savings = request.planning.available_savings if request.planning else None
    buffer = request.planning.monthly_buffer if request.planning else None
    start = max(request.month, today.strftime("%Y-%m"))
    total = savings
    points = []
    earliest = (
        start
        if scenario
        and total is not None
        and buffer is not None
        and total >= scenario["amount_minor"]
        else None
    )
    shortfalls = []
    for offset in range(24):
        month = shift_month(start, offset)
        f = forecast(db, month, inputs=inputs)
        recorded = any(line["kind"] == "receivable" for line in f["lines"])
        # A saved included purchase is already an expense. Restore it only for
        # this hypothetical earmarking calculation, so its cost is not counted twice.
        room = f["remaining"] + (
            scenario["amount_minor"]
            if scenario and scenario["already_included"] and scenario["month"] == month
            else 0
        )
        if buffer is not None and room < buffer:
            shortfalls.append(month)
        contribution = (
            max(0, room - buffer) if recorded and buffer is not None else None
        )
        total = (
            total + contribution
            if total is not None and contribution is not None
            else None
        )
        if (
            earliest is None
            and scenario
            and total is not None
            and total >= scenario["amount_minor"]
        ):
            earliest = month
        points.append(
            {
                "month": month,
                "forecast_remaining_minor": f["remaining"],
                "room_before_selected_purchase_minor": room,
                "income_recorded": recorded,
                "potential_contribution_minor": contribution,
                "hypothetical_trip_fund_minor": total,
            }
        )
    return {
        "available_savings_minor": savings,
        "monthly_buffer_minor": buffer,
        "assumptions_complete": savings is not None and buffer is not None,
        "basis": "Hypothetical funds earmarked from forecast surplus after the stated monthly buffer. Not a bank balance, payment guarantee, or automatic carry-forward. Contributions are not reserved in the saved budget and assume income is received within the month; exact payment dates are unknown.",
        "earliest_funded_month_for_selected_scenario": earliest,
        "buffer_shortfall_months": shortfalls,
        "months": points,
    }


def model_snapshot(context):
    """Compact local-only input; Python formats amounts prone to model conversion errors."""
    # The UI keeps the full snapshot. Unknown funding assumptions do not need
    # 24 repeated unknown balances in the model prompt.
    model_context = dict(context)

    def display_money(value):
        if value is None:
            return None
        return (
            context["currency"]
            + " "
            + format(
                Decimal(value) / (10 ** context["minor_unit_digits"]),
                ",." + str(context["minor_unit_digits"]) + "f",
            )
        )

    # The UI keeps the complete evidence. Share window metadata once in the
    # local prompt to leave room for forecasts within Ollama's context window.
    if history := context.get("spending_history"):
        evidence = history["categories"] or history["payees"]
        windows = evidence[0]["comparisons"] if evidence else []
        model_context["spending_history"] = {
            **history,
            "comparison_windows": [
                {
                    key: value
                    for key, value in window.items()
                    if key
                    not in ("first_month_minor", "last_month_minor", "change_minor")
                }
                for window in windows
            ],
            **{
                group: [
                    {
                        **row,
                        "comparisons": [
                            {
                                "months": change["months"],
                                "change_minor": change["change_minor"],
                            }
                            for change in row["comparisons"]
                        ],
                    }
                    for row in history[group]
                ]
                for group in ("categories", "payees")
            },
        }
    capacity = context["planning_capacity"]
    if not capacity["assumptions_complete"] or (
        context.get("savings_projection") and context["savings_projection"]["bill"]
    ):
        model_context["planning_capacity"] = {
            key: value for key, value in capacity.items() if key != "months"
        }
    if context.get("savings_projection"):
        projection = context["savings_projection"]
        model_context["savings_projection"] = {
            **projection,
            "months": [
                {
                    key: row[key]
                    for key in (
                        "month",
                        "budget_remaining_after_bill",
                        "scenario_savings",
                        "annual_payments",
                    )
                }
                for row in projection["months"]
            ],
        }

        model_context["savings_projection"]["display_summary"] = {
            key: display_money(projection[key])
            for key in (
                "starting_savings",
                "savings_floor",
                "ending_savings",
                "baseline_ending_savings",
                "lowest_savings",
                "first_bill_month_remaining",
                "total_new_bill_cost",
            )
        }
        if projection["bill"]:
            model_context["savings_projection"]["display_summary"]["monthly_bill"] = (
                display_money(projection["bill"]["amount"])
            )
    if scenario := context.get("purchase_scenario"):
        model_context["purchase_scenario"] = {
            **scenario,
            "display_summary": {
                key: display_money(scenario[key])
                for key in (
                    "amount_minor",
                    "baseline_remaining_minor",
                    "remaining_after_purchase_minor",
                )
            },
        }
    return model_context


def answer_question(model, request, context):
    # Do not pass chat, history, budget context, or model output to web research.
    public_request = PublicResearchRequest(
        use_web=request.use_web,
        research_topic=request.research_topic,
        research_confirmation=request.research_confirmation,
    )
    research = gather_research(public_request, context["current_date"])
    context["web_research"] = research
    model_context = model_snapshot(context)
    system = (
        system_instructions(request, model_context)
        + "\nBUDGET SNAPSHOT:\n"
        + json.dumps(model_context, ensure_ascii=False, separators=(",", ":"))
    )
    history = [{"role": m.role, "content": m.content[:1000]} for m in request.history]
    return chat_with_model(
        model,
        [
            {"role": "system", "content": system},
            *history,
            {"role": "user", "content": request.message},
        ],
    )
