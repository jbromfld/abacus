"""Measure advisor prompts against loopback Ollama with synthetic data only."""

import argparse
import json
import secrets
from pathlib import Path

import httpx
from abacus.advisor import model_snapshot
from abacus.advisor_prompts import system_instructions
from abacus.budget import shift_month
from abacus.local_model import available_models, ollama_url
from abacus.schemas import AdvisorIn


def synthetic_case():
    request = AdvisorIn(
        month="2026-11",
        message="Does the selected draft purchase fit this month? Reply in at most two short sentences.",
    )
    forecasts = [
        {
            "month": shift_month(request.month, i),
            "income_minor": 300000,
            "expenses_minor": 270000,
            "remaining_minor": 30000,
            "income_entries": 1,
        }
        for i in range(12)
    ]
    totals = {
        "income_minor": 300000,
        "expenses_minor": 270000,
        "remaining_minor": 30000,
        "income_recorded": True,
    }
    context = {
        "currency": "USD",
        "minor_unit_digits": 2,
        "selected_month": request.month,
        "current_date": "2026-11-08",
        "monthly_forecasts": forecasts,
        "recent_actuals": [],
        "forecast_comparison": {
            "previous_month": "2026-10",
            "month": request.month,
            "previous": totals,
            "current": totals,
            "changes": [],
            "shortfall_minor": 0,
        },
        "spending_history": {
            "months": [],
            "categories": [],
            "payees": [],
            "comparison_windows": [],
        },
        "purchase_scenario": {
            "name": "Example laptop",
            "month": request.month,
            "amount_minor": 50000,
            "already_included": False,
            "baseline_remaining_minor": 30000,
            "remaining_after_purchase_minor": -20000,
            "would_exceed_forecast": True,
        },
        "draft_purchases": [],
        "additional_drafts_omitted": 0,
        "category_guides": [],
        "savings_projection": None,
        "planning_capacity": {
            "assumptions_complete": False,
            "available_savings_minor": None,
            "monthly_buffer_minor": None,
        },
        "web_research": {"status": "disabled", "sources": [], "warnings": []},
    }
    return request, model_snapshot(context)


def measure(client, model, instructions, request, context):
    # Different equal-length markers prevent a repeated prompt from appearing
    # faster solely because the entire prefix was already cached.
    prefix = "Synthetic benchmark " + secrets.token_hex(8) + ".\n"
    system = (
        prefix
        + instructions.rstrip().removesuffix("BUDGET SNAPSHOT:").rstrip()
        + "\nBUDGET SNAPSHOT:\n"
        + json.dumps(context, separators=(",", ":"))
    )
    response = client.post(
        ollama_url() + "/api/chat",
        json={
            "model": model,
            "stream": False,
            "think": False,
            "options": {"temperature": 0, "num_predict": 128, "num_ctx": 8192},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": request.message},
            ],
        },
    )
    response.raise_for_status()
    result = response.json()
    if result.get("error") or not result.get("done"):
        raise RuntimeError("Local model did not finish the benchmark.")
    metrics = {
        key: result.get(key)
        for key in (
            "prompt_eval_count",
            "prompt_eval_cached_count",
            "eval_count",
            "done_reason",
        )
    }
    metrics.update(
        {
            key + "_seconds": round(result.get(key, 0) / 1e9, 3)
            for key in (
                "load_duration",
                "prompt_eval_duration",
                "eval_duration",
                "total_duration",
            )
        }
    )
    return {
        "instruction_characters": len(instructions),
        "instruction_words": len(instructions.split()),
        **metrics,
        "synthetic_reply": result.get("message", {}).get("content", ""),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        required=True,
        help="An installed local model; never downloaded automatically",
    )
    parser.add_argument(
        "--baseline-instructions",
        type=Path,
        help="Optional saved older instruction text for before/after comparison",
    )
    args = parser.parse_args(argv)
    if args.model not in available_models():
        parser.error("Select an installed local model.")
    request, context = synthetic_case()
    versions = []
    if args.baseline_instructions:
        versions.append(("baseline", args.baseline_instructions.read_text()))
    versions.append(("current", system_instructions(request, context)))
    with httpx.Client(timeout=300, trust_env=False, follow_redirects=False) as client:
        # Warm model loading separately from the measured prompt evaluations.
        response = client.post(
            ollama_url() + "/api/chat",
            json={
                "model": args.model,
                "stream": False,
                "think": False,
                "options": {"num_predict": 1, "num_ctx": 8192},
                "messages": [
                    {"role": "user", "content": "Synthetic benchmark warmup: say OK."}
                ],
            },
        )
        response.raise_for_status()
        for name, instructions in versions:
            print(
                json.dumps(
                    {
                        "variant": name,
                        "model": args.model,
                        **measure(client, args.model, instructions, request, context),
                    }
                ),
                flush=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
