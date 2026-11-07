"""Remember validated per-card CSV layouts without altering existing reviews."""
from .models import Account, Settings
from .schemas import MappingIn
from .imports import csv_rows, validate_rows
from .classification import apply_payee_rules


def apply_saved_mapping(db, job):
    if job.source.get('type') != 'csv' or job.source.get('mapping') or job.status not in ('prepared','review','failed','interrupted'):
        return False
    profile = db.get(Account, job.account_id).csv_mapping
    if not profile:
        return False
    try:
        mapping = MappingIn.model_validate(profile).model_dump()
        rows = csv_rows(job.source, mapping, job.period, db.get(Settings, 1).currency)
    except ValueError:
        job.source = {**job.source, 'mapping_warning':'The saved card mapping does not match this CSV. Choose its columns and apply a new mapping.'}
        return False
    job.source = {**job.source, 'mapping':mapping, 'mapping_warning':''}
    job.rows = validate_rows(db, apply_payee_rules(db, rows), job.account_id)
    job.status, job.error = 'review', ''
    return True
