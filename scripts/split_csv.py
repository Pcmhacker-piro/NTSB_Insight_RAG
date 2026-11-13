import pandas as pd
import os

import argparse

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
default_src = os.path.expanduser('~/Downloads/NTSB-AviationData.csv')
default_out_dir = os.path.join(base_dir, 'data')

parser = argparse.ArgumentParser(description="Split full NTSB CSV into year bands")
parser.add_argument('--src', default=default_src, help="Path to source CSV")
parser.add_argument('--out-dir', default=default_out_dir, help="Output directory")
args = parser.parse_args()

src = args.src
out_dir = args.out_dir
os.makedirs(out_dir, exist_ok=True)

df = pd.read_csv(src)
df['EventDate'] = pd.to_datetime(df['EventDate'], errors='coerce')
df['Year'] = df['EventDate'].dt.year

bands = [
    ('2010_2014', 2010, 2014),
    ('2015_2019', 2015, 2019),
    ('2020_2024', 2020, 2024),
    ('2025_2026', 2025, 2026),
]

for label, start, end in bands:
    subset = df[(df['Year'] >= start) & (df['Year'] <= end)].drop(columns=['Year'])
    out_path = os.path.join(out_dir, f'NTSB_{label}.csv')
    subset.to_csv(out_path, index=False)
    print(f'NTSB_{label}.csv  -> {len(subset)} records')
