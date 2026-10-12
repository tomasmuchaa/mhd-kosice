import sqlite3
import json

conn = sqlite3.connect('data/mhd_historia.db')
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [r[0] for r in c.fetchall()]
print('Tables:', tables)

for t in tables:
    c.execute(f"PRAGMA table_info({t});")
    cols = [r[1] for r in c.fetchall()]
    print(f"Table {t} cols: {cols}")
    if 'model' in cols:
        c.execute(f"SELECT DISTINCT model FROM {t} WHERE model IS NOT NULL;")
        print(f"Distinct models in {t}:", [r[0] for r in c.fetchall()])

# Also check overrides
with open('data/overrides.json', 'r', encoding='utf-8') as f:
    ov = json.load(f)
override_models = set(v.get('model') for v in ov.values() if v.get('model'))
print('Override models:', override_models)
