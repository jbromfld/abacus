"""Bounded candidate batches for user-reviewed local-model suggestions."""

import re
from collections import defaultdict

from .classification import normalize_payee

# Generic statement/organization words are not merchant identities.
STOP_WORDS = {
    "store",
    "stores",
    "market",
    "payment",
    "purchase",
    "refund",
    "online",
    "inc",
    "llc",
    "pos",
    "tst",
    "sq",
    "sp",
    "the",
    "com",
}


def candidate_batches(records, size=24, overlap=6):
    """Shared text finds candidates only. It never authorizes an alias or category."""
    parents = {row["id"]: row["id"] for row in records}

    def root(key):
        while parents[key] != key:
            parents[key] = parents[parents[key]]
            key = parents[key]
        return key

    def connect(keys):
        if not keys:
            return
        first = root(keys[0])
        for key in keys[1:]:
            parents[root(key)] = first

    buckets = defaultdict(list)
    approved = defaultdict(list)
    for row in records:
        if row["group_id"]:
            approved[row["group_id"]].append(row["id"])
        text = normalize_payee(row["payee"] + " " + (row.get("group_name") or ""))
        tokens = {
            word
            for word in text.split()
            if len(word) >= 3 and not word.isdigit() and word not in STOP_WORDS
        }
        for token in tokens:
            # Prefixes bridge spellings such as WHOLEFDS and Whole Foods. The
            # model and then the user decide; this is not automatic matching.
            buckets[(row["kind"], re.sub(r"\W", "", token)[:4])].append(row["id"])
    for keys in [*buckets.values(), *approved.values()]:
        connect(keys)
    components = defaultdict(list)
    for row in records:
        components[root(row["id"])].append(row)
    result = []
    for rows in components.values():
        if len(rows) < 2 or all(row["group_id"] for row in rows):
            continue
        rows.sort(key=lambda row: (normalize_payee(row["payee"]), row["id"]))
        for start in range(0, len(rows), size - overlap):
            batch = rows[start : start + size]
            if len(batch) >= 2:
                result.append(batch)
    return result
