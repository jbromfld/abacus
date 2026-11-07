"""Local, editable merchant matching configuration. No transaction data is changed."""
import json
import logging
from pathlib import Path
import re
from difflib import SequenceMatcher

CONFIG_PATH = Path(__file__).with_name('payee_matching.json')


def load_matching_config():
    """Read on each classification pass so edits need no server restart.

    Invalid configuration disables optional matching; basic memory still works.
    This is a trusted local Python regex configuration, not uploaded statement data.
    """
    try:
        data = json.loads(CONFIG_PATH.read_text())
        threshold = float(data['fuzzy_threshold'])
        margin = float(data['fuzzy_margin'])
        if not 0.8 <= threshold <= 1 or not 0 < margin <= 1:
            raise ValueError('threshold must be 0.8–1 and margin must be >0–1')
        patterns = []
        for entry in data['patterns']:
            pattern = re.compile(entry['pattern'], re.IGNORECASE)
            replacement = entry['replacement']
            pattern.sub(replacement, '')  # Validate replacement backreferences too.
            patterns.append((pattern, replacement))
        return patterns, threshold, margin
    except (OSError, ValueError, TypeError, KeyError, re.error, IndexError) as exc:
        logging.getLogger(__name__).warning('Payee matching config disabled: %s', exc)
        return [], 1.0, 1.0


def similar_category(payee, kind, groups, threshold, margin):
    """Abstain for short names, changed numbers, first-word changes or close rivals."""
    if threshold >= 1 or len(payee) < 12 or not payee.split():
        return None
    scores = {}
    for (candidate, candidate_kind), categories in groups.items():
        if candidate_kind != kind or len(candidate) < 12:
            continue
        if candidate.split()[0] != payee.split()[0]:
            continue
        if re.findall(r'\d+', candidate) != re.findall(r'\d+', payee):
            continue
        score = SequenceMatcher(None, payee, candidate, autojunk=False).ratio()
        for category in categories:
            scores[category] = max(scores.get(category, 0), score)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if not ranked or ranked[0][1] < threshold:
        return None
    if len(ranked) > 1 and ranked[0][1] - ranked[1][1] < margin:
        return None
    return ranked[0][0]
