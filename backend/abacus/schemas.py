from datetime import date
from typing import Literal, Annotated
from pydantic import BaseModel, Field, StringConstraints, model_validator, AfterValidator

def valid_month(value):
    if not 1900 <= int(value[:4]) <= 9998:
        raise ValueError('Choose a year from 1900 to 9998.')
    return value

Month = Annotated[str, StringConstraints(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), AfterValidator(valid_month)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Money = Annotated[int, Field(strict=True, gt=0, le=9_000_000_000_000)]
Kind = Literal['purchase', 'refund', 'fee', 'payment', 'transfer']
BillDate = Annotated[date, Field(ge=date(1900, 1, 1), le=date(9998, 12, 31))]

class CategoryIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]

class AccountIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    stale_alert_enabled: bool = False

class CardMonitoringIn(BaseModel):
    stale_alert_enabled: bool

class RecurringIn(BaseModel):
    name: Name
    kind: Literal['payable', 'receivable']
    frequency: Literal['monthly', 'annual']
    distribute_annual: bool = True
    category_id: str | None = None
    start_month: Month
    end_month: Month | None = None
    due_day: int | None = Field(default=None, ge=1, le=31)
    due_month: int | None = Field(default=None, ge=1, le=12)
    payment_tracking_start: BillDate | None = None
    ach_enabled: bool = False
    ach_day: int | None = Field(default=None, ge=1, le=31)
    ach_start_month: Month | None = None
    ach_account_id: str | None = None
    @model_validator(mode='after')
    def valid(self):
        if self.kind == 'receivable' and (self.due_day or self.due_month or self.payment_tracking_start):
            raise ValueError('Due dates and payment tracking are available for payables only.')
        if self.due_month and (self.frequency != 'annual' or not self.due_day):
            raise ValueError('An annual due month requires an annual payable and a due day.')
        if self.due_day and self.frequency == 'annual' and not self.due_month:
            self.due_month = int(self.start_month[5:])
        if self.ach_enabled:
            if self.kind != 'payable' or self.frequency != 'monthly':
                raise ValueError('Automatic ACH recording is available for monthly payables.')
            if not self.ach_day or not self.ach_start_month or not self.ach_account_id:
                raise ValueError('Choose a debit day, automatic recording start month, and bank account for ACH.')
        if self.kind == 'payable' and not self.category_id:
            raise ValueError('Choose a category for this payable.')
        if self.end_month and self.end_month < self.start_month:
            raise ValueError('End month must follow the first month.')
        return self

class RecurringCreate(RecurringIn):
    amount: Money

class BillPaymentIn(BaseModel):
    paid: bool
    paid_on: BillDate | None = None

class ChangeIn(BaseModel):
    month: Month
    amount: Money
    override: bool = False

class PurchaseIn(BaseModel):
    name: Name
    amount: Money
    month: Month
    category_id: str
    notes: str = Field(default='', max_length=2000)
    included: bool = False

class TransactionIn(BaseModel):
    date: date
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    amount: Money
    kind: Kind = 'purchase'
    category_id: str | None = None
    account_id: str
    @model_validator(mode='after')
    def valid(self):
        if self.kind not in ('payment', 'transfer') and not self.category_id:
            raise ValueError('Choose a category for spending and refunds.')
        return self

class SettingsIn(BaseModel):
    currency: Literal['USD', 'EUR', 'GBP', 'CAD', 'AUD', 'JPY', 'CHF'] = 'USD'
    model: str = Field(default='', max_length=200)
    advisor_enabled: bool = False

class MappingIn(BaseModel):
    date_column: str
    description_column: str
    amount_column: str
    date_format: Literal['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%m/%d/%y', '%m/%d'] = '%Y-%m-%d'
    positive_is: Literal['purchase', 'refund'] | None = None

class CommitIn(BaseModel):
    rows: list[dict] = Field(max_length=5000)

class CompleteIn(BaseModel):
    complete: bool

class PayeeRuleIn(BaseModel):
    category_id: str


class AdvisorMessage(BaseModel):
    role: Literal['user', 'assistant']
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]

class PurchaseScenario(BaseModel):
    name: Name = 'Potential purchase'
    amount: Money
    month: Month

class PlanningAssumptions(BaseModel):
    available_savings: Annotated[int, Field(strict=True, ge=0, le=9_000_000_000_000)] | None = None
    monthly_buffer: Annotated[int, Field(strict=True, ge=0, le=9_000_000_000_000)] | None = None


NonnegativeMoney = Annotated[int, Field(strict=True, ge=0, le=9_000_000_000_000)]

class CategoryGuideIn(BaseModel):
    monthly_guide: NonnegativeMoney | None = None

class SavingsIn(BaseModel):
    amount: NonnegativeMoney
    month: Month
    floor: NonnegativeMoney = 0

class MonthlyBillScenario(BaseModel):
    name: Name = 'Potential monthly bill'
    amount: Money
    start_month: Month
    end_month: Month | None = None

    @model_validator(mode='after')
    def valid_range(self):
        if self.end_month and self.end_month < self.start_month:
            raise ValueError('The bill’s final month must follow its starting month.')
        return self

class BillEstimateIn(MonthlyBillScenario):
    category_id: str
    due_day: int | None = Field(default=None, ge=1, le=31)

class RecurringChangeScenario(BaseModel):
    recurring_id: str = Field(max_length=36)
    action: Literal['modify', 'remove']
    start_month: Month
    end_month: Month | None = None
    amount: Money | None = None

    @model_validator(mode='after')
    def valid_change(self):
        if self.action == 'modify' and self.amount is None:
            raise ValueError('Enter the new recurring amount.')
        if self.action == 'remove' and self.amount is not None:
            raise ValueError('A removal scenario does not take a replacement amount.')
        if self.end_month and self.end_month < self.start_month:
            raise ValueError('The final scenario month must follow its starting month.')
        return self

class SavingsProjectionIn(BaseModel):
    savings: SavingsIn | None = None
    start_month: Month | None = None
    months: Literal[12, 24] = 24
    bill: MonthlyBillScenario | None = None
    estimate_id: str | None = Field(default=None, max_length=36)
    recurring_change: RecurringChangeScenario | None = None

    @model_validator(mode='after')
    def valid_scenario(self):
        if sum(value is not None for value in (self.bill,self.estimate_id,self.recurring_change)) > 1:
            raise ValueError('Preview one new bill, estimate, or recurring change at a time.')
        if self.savings is None and self.start_month is None:
            raise ValueError('Choose a planning month or provide a savings snapshot.')
        return self


class AdvisorIn(BaseModel):
    month: Month
    use_web: bool = False
    research_topic: str = Field(default='', max_length=1000)
    planning: PlanningAssumptions | None = None
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    history: list[AdvisorMessage] = Field(default_factory=list, max_length=12)
    purchase_id: str | None = Field(default=None, max_length=36)
    scenario: PurchaseScenario | None = None
    savings: SavingsIn | None = None
    monthly_bill: MonthlyBillScenario | None = None
    bill_estimate_id: str | None = Field(default=None, max_length=36)

    @model_validator(mode='after')
    def valid_context(self):
        if self.purchase_id and self.scenario:
            raise ValueError('Select a saved purchase or enter an estimate, not both.')
        if self.monthly_bill and self.bill_estimate_id:
            raise ValueError('Choose a saved bill estimate or a new monthly bill, not both.')
        if (self.monthly_bill or self.bill_estimate_id) and (self.purchase_id or self.scenario):
            raise ValueError('Preview one purchase or monthly bill scenario at a time.')
        if sum(len(m.content) for m in self.history) > 24000:
            raise ValueError('Chat history is too long. Start a new conversation.')
        return self
