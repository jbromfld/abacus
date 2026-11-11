"""Read-only local budget advice; monetary scenarios are calculated by Python."""

import json
import re
from decimal import Decimal

from sqlalchemy import select

from .advisor_history import spending_comparison, spending_history
from .advisor_prompts import system_instructions
from .budget import ActualWindow, ForecastInputs, forecast, shift_month
from .category_planning import category_averages
from .clock import local_today
from .local_model import chat_with_model
from .model_tracing import model_workflow
from .models import Category, Settings
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
                "source": line.get("source") or "recurring",
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
        "basis": "Saved forecast changes from previous_month to month, already included in current totals. These are historical edits, not proposed additional savings or evidence of actual spending reductions. Use current_expense_categories as the planned expense baseline for any further cuts.",
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
    from .planning import planning_summary

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
    if request.scenario:
        item = request.scenario
        baseline = forecast(db, item.month, inputs=inputs)
        after = baseline["remaining"] - item.amount
        scenario = {
            "name": item.name,
            "month": item.month,
            "amount_minor": item.amount,
            "already_included": False,
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
    savings_projection = advisor_savings_projection(db, request, inputs=inputs)
    guide_end = shift_month(request.month, -1)
    guide_stats = (
        category_averages(db, guide_end, categories=categories)["categories"]
        if guide_end >= "1900-12"
        else []
    )
    history = spending_history(db, request.month, today, categories)
    comparison = spending_comparison(db, history)
    goals = planning_summary(db, inputs=inputs)
    if savings_projection:
        savings_projection["scope"] = (
            "Baseline or explicit bill scenario, excluding saved Planning goals. "
            "Use planning_goals.projection for running cash including all saved goals."
        )
    selected = next(
        (row for row in goals["plans"] if row["id"] == request.plan_id), None
    )
    if request.plan_id and selected is None:
        raise ValueError(
            "The selected plan is no longer available. Open Planning to choose a current plan."
        )
    if comparison:
        comparison["budget_impact"] = []
        for period, key in (
            (comparison["previous_month"], "previous_minor"),
            (comparison["month"], "current_minor"),
        ):
            planned = inputs.forecast(period)
            income_recorded = any(
                line["kind"] == "receivable" for line in planned["lines"]
            )
            spending = comparison["totals"][key]
            comparison["budget_impact"].append(
                {
                    "month": period,
                    "planned_income_minor": planned["income"]
                    if income_recorded
                    else None,
                    "actual_spending_minor": spending,
                    "room_after_recorded_spending_minor": planned["income"] - spending
                    if income_recorded and spending is not None
                    else None,
                }
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
        },
        "monthly_forecasts": projections,
        "selected_plan": {
            "id": selected["id"],
            "name": selected["name"],
            "target_date": selected["target_date"],
            "category": selected["category"],
            "amount_minor": selected["amount"],
            "set_aside_minor": selected["set_aside"],
            "still_needed_minor": selected["still_needed"],
            "monthly_needed_minor": selected["monthly_needed"],
            "status": selected["status"],
            "updated_at": selected["updated_at"],
            "budgeted_monthly_allocation_minor": selected.get("monthly_allocation"),
            "projected_contributions_minor": selected.get("projected_contributions"),
            "projected_funding_minor": selected.get("projected_funding"),
            "funding_gap_minor": selected.get("funding_gap"),
        }
        if selected
        else None,
        "planning_goals": {
            "basis": goals["basis"],
            "savings_month": goals["savings_month"],
            "saved_savings_minor": goals["savings"],
            "set_aside_minor": goals["set_aside"],
            "free_savings_minor": goals["free_savings"],
            "total_planned_minor": goals["total_planned"],
            "plans": [
                {
                    "name": row["name"],
                    "target_date": row["target_date"],
                    "category": row["category"],
                    "amount_minor": row["amount"],
                    "set_aside_minor": row["set_aside"],
                    "still_needed_minor": row["still_needed"],
                    "budgeted_monthly_allocation_minor": row.get("monthly_allocation"),
                    "projected_contributions_minor": row.get("projected_contributions"),
                    "projected_funding_minor": row.get("projected_funding"),
                    "funding_gap_minor": row.get("funding_gap"),
                }
                for row in goals["plans"][:20]
            ],
            "additional_plans_omitted": max(0, len(goals["plans"]) - 20),
            "projection": {
                "basis": goals["projection"]["basis"],
                "income_complete": goals["projection"]["income_complete"],
                "months": [
                    {
                        "month": row["month"],
                        "balance_minor": row["balance"],
                        "plan_payments_minor": row["plan_payments"],
                    }
                    for row in goals["projection"]["months"]
                ],
            }
            if goals["projection"]
            else None,
        },
        "annual_income_estimates": [
            {
                "name": item.name,
                "year": item.year,
                "amount_minor": item.amount,
                "included": item.included,
                "basis": "Estimated extra income allocated over this calendar year when included; not verified receipts or a monthly deposit schedule.",
            }
            for item in inputs.annual_income
            if int(months[0][:4]) <= item.year <= int(months[-1][:4])
        ],
        "recent_actuals": recent,
        "spending_history": history,
        "spending_comparison": comparison,
        "forecast_comparison": forecast_comparison(
            db, request.month, inputs=inputs, categories=categories
        ),
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
        room = f["remaining"]
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


def model_snapshot(context, question=""):
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

    def display_fields(row):
        return {
            key.removesuffix("_minor") + "_display"
            if key.endswith("_minor")
            else key: display_money(value) if key.endswith("_minor") else value
            for key, value in row.items()
        }

    # The UI keeps the complete evidence. Share window metadata once in the
    # local prompt to leave room for forecasts within Ollama's context window.
    if history := context.get("spending_history"):
        evidence = history["categories"] or history["payees"]
        windows = evidence[0]["comparisons"] if evidence else []
        detailed = bool(
            re.search(r"\b(12|twelve|year|history|trend)\b", question, re.I)
        )
        count = 12 if detailed else 3
        all_months = history.get("months", [])
        selected_payees = sorted(
            history["payees"],
            key=lambda row: not bool(row["payee"].casefold() in question.casefold()),
        )[:8]
        model_context["spending_history"] = {
            "months": all_months[-count:],
            "average_window": {
                "start_month": history.get("start_month"),
                "end_month": history.get("end_month"),
                "partial_month_count": sum(
                    month["status"] == "partial" for month in all_months
                ),
            },
            "additional_payees_omitted": history.get("additional_payees_omitted", 0)
            + len(history["payees"])
            - len(selected_payees),
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
                        **{
                            key: value
                            for key, value in row.items()
                            if key not in ("monthly_net_minor", "average_minor")
                        },
                        "monthly_net_display": [
                            display_money(value)
                            for value in row["monthly_net_minor"][-count:]
                        ],
                        "average_display": display_money(row["average_minor"]),
                        "comparisons": [
                            {
                                "months": change["months"],
                                "change_display": display_money(change["change_minor"]),
                            }
                            for change in row["comparisons"]
                        ],
                    }
                    for row in (
                        selected_payees if group == "payees" else history[group]
                    )
                ]
                for group in ("categories", "payees")
            },
        }
        model_context.pop("recent_actuals", None)
    if comparison := context.get("spending_comparison"):
        model_context["spending_comparison"] = {
            **comparison,
            "totals": display_fields(comparison["totals"]),
            "accounts": [display_fields(row) for row in comparison["accounts"]],
            "categories": [display_fields(row) for row in comparison["categories"]],
            "budget_impact": [
                display_fields(row) for row in comparison.get("budget_impact", [])
            ],
        }
    if "category_guides" in context:
        model_context["category_guides"] = [
            display_fields(row)
            for row in context["category_guides"]
            if row["monthly_guide_minor"] is not None
        ]
    capacity = context["planning_capacity"]
    if not capacity["assumptions_complete"] or (
        context.get("savings_projection") and context["savings_projection"]["bill"]
    ):
        model_context["planning_capacity"] = {
            key: value for key, value in capacity.items() if key != "months"
        }
    if isinstance(context.get("monthly_forecasts"), list):
        model_context["monthly_forecasts"] = {
            "columns": ["month", "income", "expenses", "remaining", "income_entries"],
            "rows": [
                [
                    row["month"],
                    display_money(row["income_minor"]),
                    display_money(row["expenses_minor"]),
                    display_money(row["remaining_minor"]),
                    row["income_entries"],
                ]
                for row in context["monthly_forecasts"]
            ],
        }
    if context.get("savings_projection"):
        projection = context["savings_projection"]
        model_context["savings_projection"] = {
            **{key: value for key, value in projection.items() if key != "assumptions"},
            "month_columns": ["month", "budget_remaining", "savings"],
            "months": [
                [
                    row["month"],
                    display_money(row["budget_remaining_after_bill"]),
                    display_money(row["scenario_savings"]),
                ]
                for row in projection["months"]
            ],
            "annual_payments": [
                {"month": row["month"], "payments": row["annual_payments"]}
                for row in projection["months"]
                if row["annual_payments"]
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
    # No raw minor-unit amounts cross the model boundary, even in nested
    # annual payments, forecast deltas, scenarios, or savings projections.
    money_keys = {
        "amount",
        "starting_savings",
        "savings_floor",
        "ending_savings",
        "baseline_ending_savings",
        "total_new_bill_cost",
        "total_budget_change",
        "lowest_savings",
        "first_bill_month_remaining",
        "budget_remaining_after_bill",
        "scenario_savings",
    }

    def formatted_tree(value):
        if isinstance(value, list):
            return [formatted_tree(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {}
        summary = value.get("display_summary", {})
        for key, item in value.items():
            if key == "minor_unit_digits":
                continue
            if key == "display_summary":
                result[key] = {
                    name.removesuffix("_minor"): amount for name, amount in item.items()
                }
                continue
            is_money = key.endswith("_minor") or key in money_keys
            if is_money and (item is None or type(item) is int):
                if key not in summary:
                    result[key.removesuffix("_minor") + "_display"] = display_money(
                        item
                    )
            else:
                result[key] = formatted_tree(item)
        return result

    return formatted_tree(model_context)


@model_workflow("budget_advisor")
def answer_question(model, request, context):
    # Do not pass chat, history, budget context, or model output to web research.
    public_request = PublicResearchRequest(
        use_web=request.use_web,
        research_topic=request.research_topic,
        research_confirmation=request.research_confirmation,
    )
    research = gather_research(public_request, context["current_date"])
    context["web_research"] = research
    model_context = model_snapshot(context, request.message)
    system = (
        system_instructions(request, model_context)
        + "\nBUDGET SNAPSHOT:\n"
        + json.dumps(model_context, ensure_ascii=False, separators=(",", ":"))
    )
    # Keep the newest exchanges; very long conversations must not crowd out
    # the fresh budget snapshot or the answer in the local model's context.
    history = []
    remaining = max(0, min(3000, 20000 - len(system) - len(request.message)))
    for message in reversed(request.history):
        content = message.content[: min(1000, remaining)]
        if not content:
            break
        history.insert(0, {"role": message.role, "content": content})
        remaining -= len(content)
    return chat_with_model(
        model,
        [
            {"role": "system", "content": system},
            *history,
            {"role": "user", "content": request.message},
        ],
    )
