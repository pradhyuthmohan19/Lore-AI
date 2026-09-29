import sys
from seed_data import load_rows, series_facts
from memory import retain_many

csv_path, bank = sys.argv[1], sys.argv[2]
for label, facts in series_facts(load_rows(csv_path)):
    for f in facts:
        print(" *", f)
    retain_many(facts, bank_id=bank)