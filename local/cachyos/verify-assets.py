#!/usr/bin/env python3
"""Verify all nine fixed assets before host installation (no network)."""
from pathlib import Path
import hashlib,json,sys
root=Path(__file__).resolve().parents[2];assets=Path(sys.argv[1]);m=json.loads((root/'firmware/artifacts-610.43.03.json').read_text())
pins=dict(m['derived_assets']);pins['gsp_ga10x.bin']=m['source_artifacts'][2]['firmware'][0]['sha256']
for key in ('generated_payload','generated_ad102_payload'):
 e=m[key];pins[e['filename']]=e['sha256']
if len(pins)!=9:raise SystemExit('expected 9 pinned assets')
for name,expected in sorted(pins.items()):
 f=assets/name
 if not f.is_file() or f.is_symlink() or hashlib.sha256(f.read_bytes()).hexdigest()!=expected:raise SystemExit('Invalid pinned asset: '+name)
 print(name+': OK')
