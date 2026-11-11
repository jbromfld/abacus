"""Read-only web-search adapters. Budget snapshots are never passed to providers."""

import html
import ipaddress
import json
import re
from datetime import UTC, date, datetime
from hashlib import sha256
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .config import local_config


class PublicResearchRequest(BaseModel):
    """Only explicitly approved public fields cross into the search adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    use_web: bool = False
    research_topic: str = ""
    research_confirmation: str = ""


class ResearchPlan(BaseModel):
    queries: list[str] = Field(default_factory=list, max_length=3)
    missing_details: list[str] = Field(default_factory=list, max_length=6)


def research_status():
    config = local_config()
    ready = bool(config.get("BRAVE_SEARCH_API_KEY", "").strip())
    return {
        "provider": "brave",
        "available": ready,
        "message": ""
        if ready
        else "Set BRAVE_SEARCH_API_KEY in .env to enable Brave web research.",
    }


def clean_text(value, limit):
    return re.sub(
        r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", "", str(value or "")))
    ).strip()[:limit]


def public_source_url(value):
    try:
        url = urlsplit(value)
        host = (url.hostname or "").lower()
        _ = url.port  # Validate malformed/out-of-range ports before returning links.
        if len(value) > 2000:
            return None
        if (
            url.scheme not in ("http", "https")
            or not host
            or url.username
            or url.password
        ):
            return None
        if (
            host == "localhost"
            or host.endswith((".localhost", ".local", ".internal"))
            or "." not in host
        ):
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            pass
        return value[:2000]
    except (ValueError, TypeError):
        return None


def safe_query(query):
    value = " ".join(query.split())
    if not value or len(value) > 280 or len(value.split()) > 50:
        return None
    # Reject common financial/identity leakage from local query planning. The
    # planner has no access to the database snapshot in the first place.
    if re.search(
        r"[$€£¥@]|\d{8,}|\b(?:\d[ .-]?){8,}\d\b|\b(income|salary|paycheck|savings|balance|password|account|social security|ssn|debt|credit[ -]?card|owe|owed|iban|routing|mortgage|financial|afford|budget)\b",
        value,
        re.IGNORECASE,
    ):
        return None
    return value


def confirmation_for(plan, topic):
    return sha256(
        json.dumps({"topic": topic, "queries": plan.queries}, sort_keys=True).encode()
    ).hexdigest()


def plan_research(topic, current_date):
    """Prepare explicit public topic only; private chat/history never enter queries."""
    today = date.fromisoformat(current_date)
    raw = topic.strip()
    if not raw or not safe_query(raw):
        return ResearchPlan(
            missing_details=[
                "Enter a public travel topic with destination and dates, without private financial or identity details."
            ]
        )
    details = []
    if not re.search(
        r"\b(travel|trip|vacation|holiday|weekend|flight|hotel|lodging|resort|cruise|july|august|miami|vallarta)\b",
        raw,
        re.I,
    ):
        return ResearchPlan(
            queries=[
                raw[:180] + " official specifications price",
                raw[:180] + " official buying guide availability",
            ],
            missing_details=[
                "Confirm product requirements, region and currency before treating an advertised price as a usable estimate."
            ],
        )

    def season(match):
        modifier, name = match.group(1).lower(), match.group(2).lower()
        year = today.year + (1 if modifier == "next" else 0)
        details.append(
            f"Confirm {name} {year} as the intended season and choose an exact Friday–Sunday weekend."
        )
        return f"{name} {year}"

    raw = re.sub(
        r"\b(next|this)\s+(spring|summer|fall|autumn|winter)\b",
        season,
        raw,
        flags=re.IGNORECASE,
    )
    raw = re.sub(r"\bnext year\b", str(today.year + 1), raw, flags=re.IGNORECASE)
    topic = " ".join(raw.split())[:180]
    if not safe_query(topic):
        return ResearchPlan(
            missing_details=[
                "Enter public travel details without financial or identity information."
            ]
        )
    if not details:
        details.append(
            "Confirm exact travel dates or the Friday–Sunday weekend; month/season alone does not establish bookable rates."
        )
    if not re.search(
        r"\b(?:\d+|one|two|three|four|solo)\s+(?:travelers|people|adults|guests)|\bsolo\b",
        raw,
        re.IGNORECASE,
    ):
        details.append("How many travelers and rooms?")
    if not re.search(r"\bfrom\s+\w+", raw, re.IGNORECASE):
        details.append("Where will you depart from, and will you drive or fly?")
    details.append(
        "Confirm the precise destination area, room preferences, meal requirements, and any dates or locations to avoid."
    )
    queries = [
        topic + " hotels vacation rentals official rates",
        topic + " restaurants menus meal prices",
        topic + " transport travel costs booking planning",
    ]
    return ResearchPlan(queries=queries, missing_details=details[:6])


def search_query(query):
    config = local_config()
    status = research_status()
    if not status["available"]:
        raise ValueError(status["message"])
    with httpx.Client(
        timeout=httpx.Timeout(12, connect=5), trust_env=False, follow_redirects=False
    ) as client:
        response = client.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": config["BRAVE_SEARCH_API_KEY"],
            },
            params={
                "q": query,
                "count": 4,
                "extra_snippets": "true",
                "safesearch": "moderate",
            },
        )
        response.raise_for_status()
        records = response.json().get("web", {}).get("results", [])[:4]
        return [
            {
                "title": r.get("title"),
                "url": r.get("url"),
                "snippet": " ".join(
                    [r.get("description") or "", *(r.get("extra_snippets") or [])[:2]]
                ),
            }
            for r in records
        ]


def gather_research(request: PublicResearchRequest, current_date):
    result = {
        "status": "disabled",
        "provider": research_status()["provider"],
        "queries": [],
        "missing_details": [],
        "sources": [],
        "warnings": [],
    }
    if not request.use_web:
        return result
    if not research_status()["available"]:
        result.update(status="unavailable", warnings=[research_status()["message"]])
        return result
    try:
        plan = plan_research(request.research_topic, current_date)
    except Exception:
        result.update(
            status="failed",
            warnings=[
                "Could not prepare web research. Try a specific destination/date or add a short research topic. No web information was retrieved."
            ],
        )
        return result
    result["missing_details"] = [clean_text(v, 250) for v in plan.missing_details]
    result["queries"] = list(
        dict.fromkeys(q for query in plan.queries if (q := safe_query(query)))
    )[:3]
    if not result["queries"]:
        result.update(
            status="needs_details",
            warnings=[
                "No suitable public travel search terms were generated. Clarify the destination, dates, and travel preferences."
            ],
        )
        return result
    if request.research_confirmation != confirmation_for(plan, request.research_topic):
        result.update(
            status="needs_confirmation",
            warnings=[
                "Preview and confirm the public search terms before researching. Private chat is never used to construct queries."
            ],
        )
        return result
    seen = set()
    failures = 0
    for query in result["queries"]:
        try:
            records = search_query(query)
        except Exception:
            failures += 1
            continue
        for record in records:
            url = public_source_url(record.get("url"))
            if not url or url in seen:
                continue
            seen.add(url)
            result["sources"].append(
                {
                    "id": "S" + str(len(result["sources"]) + 1),
                    "title": clean_text(record.get("title"), 180) or url,
                    "url": url,
                    "snippet": clean_text(record.get("snippet"), 1400),
                    "retrieved_at": datetime.now(UTC).isoformat(),
                }
            )
    result["status"] = (
        "partial"
        if failures and result["sources"]
        else "failed"
        if failures
        else "complete"
        if result["sources"]
        else "empty"
    )
    if result["sources"]:
        result["warnings"].append(
            "Search excerpts support research, not verified prices or availability for your dates. Confirm rates, fees, and terms with the provider before booking."
        )
    if failures:
        result["warnings"].append(
            "Some or all searches failed. Check the configured search service, API key, and quota. No live prices or availability were verified."
        )
    if not result["sources"]:
        result["warnings"].append(
            "No usable web sources were retrieved; do not treat the response as current travel research."
        )
    return result
