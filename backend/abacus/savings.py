"""Deterministic month-end savings scenarios. No model calls or budget mutations."""
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
import re
from sqlalchemy import select
from .models import Settings, Recurring, AmountChange, BillEstimate
from .schemas import SavingsIn, SavingsProjectionIn, MonthlyBillScenario
from .budget import forecast, scheduled_amount, effective_change, annual_due_month, shift_month
from .card_alerts import local_today


def savings_settings(db):
    settings = db.get(Settings,1)
    return {'amount':settings.savings_balance,'month':settings.savings_month or local_today().strftime('%Y-%m'),
            'floor':settings.savings_floor}


def infer_monthly_bill(message, month, currency):
    """Recognize a narrow amount + 'monthly bill' phrase; abstain on ambiguity.

    Explicit dates/terms need structured fields rather than guessed timing.
    """
    if re.search(r'\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|next\s+(?:month|year)|20\d{2}|for\s+\d+\s+months?|until|starting|beginning)\b',message,re.I):
        return None
    if re.search(r'[-−]\s*(?:USD|CAD|AUD|EUR|GBP|JPY|CHF|[$€£])?\s*\d',message,re.I):return None
    pattern = r'(?<![\w.,$€£-])(?P<currency>USD|CAD|AUD|EUR|GBP|JPY|CHF|[$€£])?\s*(?P<amount>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?)\s+(?:monthly\s+(?:bill|expense|payment|subscription)|(?:bill|expense|payment|subscription)\s+(?:per|a)\s+month)\b'
    matches = list(re.finditer(pattern,message,re.I))
    if len(matches) != 1:
        return None
    token = (matches[0]['currency'] or currency).upper()
    valid = {currency}
    if currency in ('USD','CAD','AUD'):valid.add('$')
    if currency == 'EUR':valid.add('€')
    if currency == 'GBP':valid.add('£')
    if token not in valid:
        return None
    try:
        value = Decimal(matches[0]['amount'].replace(',','')) * (1 if currency=='JPY' else 100)
        if value != value.to_integral_value():return None
        return MonthlyBillScenario(amount=int(value),start_month=month)
    except (InvalidOperation,ValueError):
        return None


def cash_timing(month, expenses, schedules, changes, excluded_id=None):
    payments, removed = [], 0
    for item in schedules:
        if item.id == excluded_id or month < item.start_month or (item.end_month and month > item.end_month):continue
        if not item.due_day or not item.due_month:continue
        if item.distribute_annual:
            allocation = scheduled_amount(item,changes,month)
            expenses -= allocation
            removed += allocation
        if month[5:] == annual_due_month(item):
            change = effective_change(item,changes,month)
            payment = change.amount if change else 0
            if item.distribute_annual:expenses += payment
            if payment:payments.append({'name':item.name,'amount':payment})
    return expenses, payments, removed


def project_savings(db, request):
    known = request.savings is not None
    start = request.savings.month if known else request.start_month
    opening = request.savings.amount if known else 0
    floor = request.savings.floor if known else 0
    if int(shift_month(start,request.months-1).split('-')[0]) > 9998:
        raise ValueError('The projection must end by December 9998.')
    bill = request.bill
    included = False
    if request.estimate_id:
        estimate = db.get(BillEstimate,request.estimate_id)
        if estimate is None:raise LookupError('Bill estimate not found.')
        if estimate.included and not estimate.recurring_id:
            raise ValueError('The recurring bill for this estimate was removed. Create a new estimate to preview it again.')
        bill = MonthlyBillScenario(name=estimate.name,amount=estimate.amount,start_month=estimate.start_month,end_month=estimate.end_month)
        included = estimate.included
    edit = request.recurring_change
    target = db.get(Recurring,edit.recurring_id) if edit else None
    if edit and target is None:raise LookupError('Recurring account not found.')
    if target and target.kind != 'payable':raise ValueError('Choose a recurring payable to modify or remove.')
    schedules = db.scalars(select(Recurring).where(Recurring.kind=='payable',Recurring.frequency=='annual')).all()
    changes = db.scalars(select(AmountChange)).all()
    modified = changes
    if edit and edit.action == 'modify':
        # Simulate the same effective default as Adjust amount: preserve earlier
        # months, explicit overrides, and later scheduled rate changes.
        modified = [c for c in changes if not (c.recurring_id==target.id and c.month==edit.start_month and not c.override)]
        modified.append(SimpleNamespace(recurring_id=target.id,month=edit.start_month,amount=edit.amount,override=False))
    baseline = scenario = opening
    points, missing_income, negative_months, below_floor, budget_deficits = [], [], [], [], []
    total_cost = total_change = active_months = 0
    first_active = first_active_month = None
    for offset in range(request.months):
        month = shift_month(start,offset)
        values = forecast(db,month)
        income_recorded = any(line['kind']=='receivable' for line in values['lines'])
        if not income_recorded:missing_income.append(month)
        cash_expenses, base_payments, removed = cash_timing(month,values['expenses'],schedules,changes)
        bill_active = bill is not None and month>=bill.start_month and (bill.end_month is None or month<=bill.end_month)
        extra = bill.amount if bill_active and not included else 0
        change_active = bool(edit and month>=edit.start_month and (edit.end_month is None or month<=edit.end_month)
                             and month>=target.start_month and (target.end_month is None or month<=target.end_month))
        delta = 0
        if change_active:
            before = scheduled_amount(target,changes,month)
            after = 0 if edit.action=='remove' else scheduled_amount(target,modified,month)
            delta = after-before
        adjusted_expenses = values['expenses']+delta
        scenario_cash, annual_payments, _ = cash_timing(month,adjusted_expenses,schedules,
            modified if change_active else changes,target.id if change_active and edit.action=='remove' else None)
        budget_remaining = values['income']-adjusted_expenses-extra
        cash_remaining = values['income']-scenario_cash-extra
        if bill_active or change_active:
            active_months += 1
            if first_active is None:
                first_active, first_active_month = budget_remaining, month
        total_cost += extra
        total_change += delta+extra
        baseline += values['income']-cash_expenses
        scenario += cash_remaining
        if known and scenario<0:negative_months.append(month)
        if known and scenario<floor:below_floor.append(month)
        if budget_remaining<0:budget_deficits.append(month)
        points.append({'month':month,'income':values['income'],'income_recorded':income_recorded,
            'forecast_expenses':values['expenses'],'forecast_remaining':values['remaining'],
            'scenario_forecast_expenses':adjusted_expenses+extra,
            'cash_expenses':cash_expenses,'scenario_cash_expenses':scenario_cash+extra,
            'distributed_allocation_removed':removed,'baseline_annual_payments':base_payments,
            'annual_payments':annual_payments,'extra_bill':extra,'budget_expense_change':delta+extra,
            'budget_remaining_after_bill':budget_remaining,'cash_remaining_after_bill':cash_remaining,
            'baseline_savings':baseline if known else None,'scenario_savings':scenario if known else None})
    minimum = min([opening,*[p['scenario_savings'] for p in points]]) if known else None
    lowest = next((p['month'] for p in points if p['scenario_savings']==minimum),start) if known else None
    breaches = ([start] if known and opening<floor else [])+below_floor
    first_negative = negative_months[0] if negative_months else None
    if missing_income:status='missing_income'
    elif (bill or edit) and not active_months:status='outside_horizon'
    elif not known:status='budget_only'
    elif first_negative:status='negative_savings'
    elif breaches:status='below_floor'
    elif any(p['cash_remaining_after_bill']<0 for p in points):status='uses_savings'
    else:status='fits'
    return {'currency':db.get(Settings,1).currency,'starting_savings':opening if known else None,
        'savings_known':known,'start_month':start,'savings_floor':floor,'horizon_months':request.months,
        'bill':{**bill.model_dump(),'already_included':included} if bill else None,
        'recurring_change':{**edit.model_dump(),'name':target.name,'frequency':target.frequency} if edit else None,
        'status':status,'income_complete':not missing_income,'missing_income_months':missing_income,
        'ending_savings':scenario if known else None,'baseline_ending_savings':baseline if known else None,
        'total_new_bill_cost':total_cost,'total_budget_change':total_change,
        'lowest_savings':minimum,'lowest_month':lowest,'first_negative_month':first_negative,
        'first_below_floor_month':breaches[0] if breaches else None,'budget_deficit_months':budget_deficits,
        'first_bill_month_remaining':first_active,
        'first_active_month':first_active_month,
        'assumptions':['Savings, when supplied, is a user-entered balance at the start of the planning month.',
            'Full-month forecast income and expenses; no interest, inflation, or intra-month payment timing.',
            'Dated distributed annual bills replace their monthly allocation with one full payment in the due month.',
            'Undated annual allowances keep their existing budget timing; actual spending is not added again.',
            'Savings carry forward only in this hypothetical projection; saved monthly budgets remain independent.',
            'Recurring changes are preview-only. Amount changes preserve existing overrides and later scheduled rate changes.'],
        'months':points}


def advisor_savings_projection(db, request):
    saved = savings_settings(db)
    savings = request.savings or (SavingsIn(**saved) if saved['amount'] is not None else None)
    bill = request.monthly_bill
    inferred = False
    if not bill and not request.bill_estimate_id and not request.purchase_id and not request.scenario:
        bill = infer_monthly_bill(request.message,request.month,db.get(Settings,1).currency)
        inferred = bill is not None
    if savings is None and bill is None and not request.bill_estimate_id:return None
    result = project_savings(db,SavingsProjectionIn(savings=savings,start_month=request.month,bill=bill,estimate_id=request.bill_estimate_id))
    result['bill_inferred_from_question'] = inferred
    return result
