import csv,sys
from pathlib import Path
base=Path(__file__).resolve().parent
stock=sorted(base.glob('stock-*/summary.csv'))[-1]
unlocked=sorted(base.glob('unlocked-*/summary.csv'))[-1]
def load(p):
 return {(r['uuid'],r['mode'],r['n']):r for r in csv.DictReader(p.open())}
a,b=load(stock),load(unlocked)
if a.keys()!=b.keys():raise SystemExit('GPU/mode/size mismatch')
print('| GPU | Mode | N | Stock TF/s | After TF/s | Change |\n|---|---|---|---|---|---|')
for k,r in a.items():
 x=float(r['median_tflops']);y=float(b[k]['median_tflops'])
 print(f"| {r['gpu']} | {r['mode']} | {r['n']} | {x:.2f} | {y:.2f} | {(y/x-1)*100:+.1f}% |")
