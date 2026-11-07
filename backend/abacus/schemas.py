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
    ach_enabled: bool = False
    ach_day: int | None = Field(default=None, ge=1, le=31)
    ach_start_month: Month | None = None
    ach_account_id: str | None = None
    @model_validator(mode='after')
    def valid(self):
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


class AdvisorIn(BaseModel):
    month: Month
    use_web: bool = False
    research_topic: str = Field(default='', max_length=1000)
    planning: PlanningAssumptions | None = None
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    history: list[AdvisorMessage] = Field(default_factory=list, max_length=12)
    purchase_id: str | None = Field(default=None, max_length=36)
    scenario: PurchaseScenario | None = None

    @model_validator(mode='after')
    def valid_context(self):
        if self.purchase_id and self.scenario:
            raise ValueError('Select a saved purchase or enter an estimate, not both.')
        if sum(len(m.content) for m in self.history) > 24000:
            raise ValueError('Chat history is too long. Start a new conversation.')
        return self
