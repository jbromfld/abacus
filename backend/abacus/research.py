"""Read-only web-search adapters. Budget snapshots are never passed to providers."""
from datetime import datetime, timezone, date
import html
import ipaddress
import re
from urllib.parse import urlsplit
import httpx
from pydantic import BaseModel, Field
from .config import local_config


class ResearchPlan(BaseModel):
    queries: list[str] = Field(default_factory=list, max_length=3)
    missing_details: list[str] = Field(default_factory=list, max_length=6)


def research_status():
    config = local_config()
    ready = bool(config.get('BRAVE_SEARCH_API_KEY', '').strip())
    return {'provider': 'brave', 'available': ready, 'message': '' if ready else 'Set BRAVE_SEARCH_API_KEY in .env to enable Brave web research.'}


def clean_text(value, limit):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', '', str(value or '')))).strip()[:limit]


def public_source_url(value):
    try:
        url = urlsplit(value)
        host = (url.hostname or '').lower()
        if url.scheme not in ('http', 'https') or not host or url.username or url.password:
            return None
        if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')) or '.' not in host:
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
    value = ' '.join(query.split())
    if not value or len(value) > 280 or len(value.split()) > 50:
        return None
    # Reject common financial/identity leakage from local query planning. The
    # planner has no access to the database snapshot in the first place.
    if re.search(r'[$€£¥@]|\d{8,}|\b(income|salary|paycheck|savings|balance|password|account number|social security)\b', value, re.I):
        return None
    return value


def plan_research(model, request, current_date):
    """Build bounded queries from user text, never model-invented trip details.

    No database snapshot, model call, cash inputs, or assistant history is used.
    A public research topic overrides discussion for explicit query control.
    """
    today = date.fromisoformat(current_date)
    discussion = [m.content for m in request.history if m.role == 'user'] + [request.message]
    travel_words = r'\b(trip|travel|weekend|vacation|hotel|airbnb|accommodation|visit|visiting)\b'
    candidates = [text for text in discussion if re.search(travel_words, text, re.I)]
    raw = request.research_topic.strip() or (candidates[-1] if candidates else '')
    if not raw:
        return ResearchPlan(missing_details=['What destination, date window, and travel style should I research?'])
    details = []
    def season(match):
        modifier, name = match.group(1).lower(), match.group(2).lower()
        year = today.year + (1 if modifier == 'next' else 0)
        details.append(f'Confirm {name} {year} as the intended season and choose an exact Friday–Sunday weekend.')
        return f'{name} {year}'
    raw = re.sub(r'\b(next|this)\s+(spring|summer|fall|autumn|winter)\b', season, raw, flags=re.I)
    raw = re.sub(r'\bnext year\b', str(today.year+1), raw, flags=re.I)
    # Financial sentences are for local reasoning, not for external search.
    # The explicit public topic is still filtered for financial/identity terms.
    public = []
    for sentence in re.split(r'[.!?;\n]+', raw):
        sentence = sentence.strip()
        if not sentence or re.search(r'[$€£¥@]|\b(income|salary|paycheck|savings|balance|password|account|afford|comfortable|financially|financial|budget|mortgage)\b', sentence, re.I):
            continue
        public.append(sentence)
    topic = ' '.join(public)
    topic = re.sub(r"^(?:I(?:'d| would)? (?:want|like)(?: to)? |I have |I(?:'m| am) planning )", '', topic, flags=re.I)
    topic = re.sub(r'\s+', ' ', topic).strip()[:180]
    if not topic or not safe_query(topic):
        return ResearchPlan(missing_details=['Enter a public travel topic with destination and dates, without personal financial details.'])
    if not details:
        details.append('Confirm exact travel dates or the Friday–Sunday weekend; month/season alone does not establish bookable rates.')
    if not re.search(r'\b(?:\d+|one|two|three|four|solo)\s+(?:travelers|people|adults|guests)|\bsolo\b', raw, re.I):
        details.append('How many travelers and rooms?')
    if not re.search(r'\bfrom\s+\w+', raw, re.I):
        details.append('Where will you depart from, and will you drive or fly?')
    details.append('Confirm the precise destination area, room preferences, meal requirements, and any dates or locations to avoid.')
    queries = [
        topic+' hotels vacation rentals official rates',
        topic+' restaurants menus meal prices',
        topic+' transport travel costs booking planning',
    ]
    return ResearchPlan(queries=queries, missing_details=details[:6])


def search_query(query):
    config = local_config()
    status = research_status()
    if not status['available']:
        raise ValueError(status['message'])
    with httpx.Client(timeout=httpx.Timeout(12, connect=5), trust_env=False, follow_redirects=False) as client:
        response = client.get('https://api.search.brave.com/res/v1/web/search',
            headers={'Accept':'application/json','X-Subscription-Token':config['BRAVE_SEARCH_API_KEY']},
            params={'q':query,'count':4,'extra_snippets':'true','safesearch':'moderate'})
        response.raise_for_status()
        records = response.json().get('web', {}).get('results', [])[:4]
        return [{'title':r.get('title'), 'url':r.get('url'), 'snippet':' '.join([r.get('description') or '', *(r.get('extra_snippets') or [])[:2]])} for r in records]


def gather_research(model, request, current_date):
    result = {'status':'disabled', 'provider':research_status()['provider'], 'queries':[], 'missing_details':[], 'sources':[], 'warnings':[]}
    if not request.use_web:
        return result
    if not research_status()['available']:
        result.update(status='unavailable', warnings=[research_status()['message']])
        return result
    try:
        plan = plan_research(model, request, current_date)
    except Exception:
        result.update(status='failed', warnings=['Could not prepare web research. Try a specific destination/date or add a short research topic. No web information was retrieved.'])
        return result
    result['missing_details'] = [clean_text(v, 250) for v in plan.missing_details]
    result['queries'] = list(dict.fromkeys(q for query in plan.queries if (q := safe_query(query))))[:3]
    if not result['queries']:
        result.update(status='needs_details', warnings=['No suitable public travel search terms were generated. Clarify the destination, dates, and travel preferences.'])
        return result
    seen = set()
    failures = 0
    for query in result['queries']:
        try:
            records = search_query(query)
        except Exception:
            failures += 1
            continue
        for record in records:
            url = public_source_url(record.get('url'))
            if not url or url in seen:
                continue
            seen.add(url)
            result['sources'].append({
                'id':'S'+str(len(result['sources'])+1),
                'title':clean_text(record.get('title'), 180) or url,
                'url':url, 'snippet':clean_text(record.get('snippet'), 1400),
                'retrieved_at':datetime.now(timezone.utc).isoformat(),
            })
    result['status'] = 'partial' if failures and result['sources'] else 'failed' if failures else 'complete' if result['sources'] else 'empty'
    if result['sources']:
        result['warnings'].append('Search excerpts support research, not verified prices or availability for your dates. Confirm rates, fees, and terms with the provider before booking.')
    if failures:
        result['warnings'].append('Some or all searches failed. Check the configured search service, API key, and quota. No live prices or availability were verified.')
    if not result['sources']:
        result['warnings'].append('No usable web sources were retrieved; do not treat the response as current travel research.')
    return result
