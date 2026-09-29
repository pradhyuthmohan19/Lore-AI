import sys
from memory import create_mental_model

bank = sys.argv[1]
create_mental_model(
    "brand-voice", "Brand Voice Profile",
    "What is this creator's tone, caption style, recurring themes, and which hook patterns and posting habits drive the most engagement?",
    bank_id=bank,
)