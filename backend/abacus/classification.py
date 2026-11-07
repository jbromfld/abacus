"""Fast local classification from reviewed labels; no network/model calls here."""
from collections import defaultdict
import re
import json
import unicodedata
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert
from .models import PayeeRule, Transaction
from .payee_matching import load_matching_config, similar_category


def exact_payee(description: str) -> str:
    """Keep a specific merchant variant for explicit label corrections."""
    text = unicodedata.normalize('NFKC', description).casefold()
    return re.sub(r'\s+', ' ', text).strip()


def normalize_payee(description: str, patterns=None) -> str:
    """Group merchant variants without changing original transaction/CSV data."""
    text = exact_payee(description)
    if patterns is None:
        patterns = load_matching_config()[0]
    for pattern, replacement in patterns:
        text = pattern.sub(replacement, text)
    # Dates and years at the beginning commonly label annual events, not payees.
    text = re.sub(r'^(?:(?:19|20)\d{2}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/](?:19|20)\d{2})[\s:|_-]+(?=\S)', '', text)
    text = re.sub(r'^(?:19|20)\d{2}[\s:|/_-]+(?=\S)', '', text)
    # Explicit #store markers are metadata. Unmarked numbers such as 7-Eleven,
    # Studio 54, or Route 66 remain significant.
    text = re.sub(r'#\s*\d+[a-z]?\b', ' ', text)
    text = re.sub(r"['’]", '', text)
    text = re.sub(r'[^\w\s]|_', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def learn_labels(db, rows):
    """Only call for explicitly saved/reviewed labels, never raw model output.

    Conflicting labels for a payee/type in one save remove its remembered rule.
    A later explicit correction replaces that payee/type's earlier category.
    """
    labels = defaultdict(set)
    for row in rows:
        if row.get('category_id') and row.get('kind') in ('purchase', 'refund', 'fee'):
            key = exact_payee(row['description'])
            if key and len(key) <= 500:
                labels[(key, row['kind'])].add(row['category_id'])
    for (payee, kind), categories in labels.items():
        if len(categories) != 1:
            db.execute(delete(PayeeRule).where(PayeeRule.payee == payee, PayeeRule.kind == kind))
            continue
        category_id = next(iter(categories))
        statement = insert(PayeeRule).values(payee=payee, kind=kind, category_id=category_id)
        db.execute(statement.on_conflict_do_update(
            index_elements=['payee', 'kind'], set_={'category_id': category_id}))


def apply_description_defaults(rows):
    """Default imported PAYMENT descriptions before category/model suggestions.

    Explicit review changes take precedence, so unusual matches can be corrected.
    """
    for row in rows:
        if row.get('classification') != 'manual' and 'payment' in row.get('description', '').casefold():
            row['kind'] = 'payment'
            row['category_id'] = None
            row['classification'] = 'description_keyword'
    return rows


def apply_payee_rules(db, rows):
    apply_description_defaults(rows)
    patterns, threshold, margin = load_matching_config()
    remembered = db.scalars(select(PayeeRule)).all()
    rules = {(exact_payee(r.payee), r.kind): r.category_id for r in remembered}
    groups = defaultdict(set)
    for rule in remembered:
        key = normalize_payee(rule.payee, patterns)
        if key:
            groups[(key, rule.kind)].add(rule.category_id)
    for row in rows:
        # Preserve explicit edits, CSV sign mapping, and the row's transaction type.
        if row.get('category_id'):
            continue
        kind = row.get('kind', 'purchase')
        key = (exact_payee(row.get('description', '')), kind)
        if key in rules:
            row['category_id'] = rules[key]
            row['classification'] = 'remembered_payee'
            continue
        normalized = normalize_payee(row.get('description', ''), patterns)
        candidates = groups.get((normalized, kind), set())
        if len(candidates) == 1:
            row['category_id'] = next(iter(candidates))
            row['classification'] = 'normalized_payee'
        elif not candidates:
            category = similar_category(normalized, kind, groups, threshold, margin)
            if category:
                row['category_id'] = category
                row['classification'] = 'similar_payee'
    return rows


def predict_unknown(description: str, kind: str) -> str | None:
    """Future trained-classifier hook; return category ID or abstain with None.

    This intentionally does not guess. See training/README.md for the training,
    evaluation, confidence threshold, and integration contract.
    """
    return None


def export_examples(db, output):
    """Export saved reviewed examples only; callers choose the local destination."""
    count = 0
    for item in db.scalars(select(Transaction).where(
        Transaction.category_id.is_not(None),
        Transaction.kind.in_(['purchase', 'refund', 'fee']),
    ).order_by(Transaction.date, Transaction.id)):
        output.write(json.dumps({
            'description': item.description,
            'payee': normalize_payee(item.description),
            'kind': item.kind,
            'category_id': item.category_id,
            'date': item.date.isoformat(),
        }, ensure_ascii=False) + '\n')
        count += 1
    return count
