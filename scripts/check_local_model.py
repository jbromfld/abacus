"""Optional budget-chat smoke check with synthetic data only; never a database."""
import sys
from abacus.local_model import chat_with_model

model = sys.argv[1] if len(sys.argv) > 1 else 'granite4.2:3b'
reply = chat_with_model(model, [
    {'role':'system','content':'You are a concise budgeting assistant. Use only the supplied synthetic numbers. No tools are available. All amounts below are USD.'},
    {'role':'user','content':'Synthetic forecast: income 3000, expenses 2700, remaining 300. A draft purchase costs 500, leaving -200. Does it fit this month? Reply in one sentence.'},
])
print(reply)
print(f'{model}: local chat response received; inspect the recommendation above.')
