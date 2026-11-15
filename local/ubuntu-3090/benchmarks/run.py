import csv,os,subprocess,sys,time,statistics,json,hashlib
from pathlib import Path
base=Path(__file__).resolve().parent
label=sys.argv[1] if len(sys.argv)>1 else 'stock'
if label not in ('stock','unlocked'):raise SystemExit('use stock or unlocked')
out=base/(label+'-'+time.strftime('%Y%m%d-%H%M%S'));out.mkdir()
def capture(args):return subprocess.check_output(args,text=True)
(out/'environment.txt').write_text(capture(['uname','-a'])+capture(['cat','/proc/cmdline'])+capture(['nvidia-smi','-q'])+capture(['/usr/local/cuda-12.2/bin/nvcc','--version']))
(out/'binary.sha256').write_text(hashlib.sha256((base/'bench').read_bytes()).hexdigest()+'  bench\n')
gpus=list(csv.reader(capture(['nvidia-smi','--query-gpu=index,uuid,pci.bus_id','--format=csv,noheader']).splitlines()))
rows=[]
for index,uuid,bus in gpus:
 index,uuid,bus=index.strip(),uuid.strip(),bus.strip()
 busy=capture(['nvidia-smi','--query-compute-apps=pid,gpu_uuid','--format=csv,noheader']).strip()
 if busy:raise SystemExit('GPU tasks detected; aborting: '+busy)
 env=dict(os.environ,CUDA_VISIBLE_DEVICES=uuid);env.pop('NVIDIA_TF32_OVERRIDE',None)
 with (out/f'gpu{index}-telemetry.csv').open('w') as t,(out/f'gpu{index}.csv').open('w') as f,(out/f'gpu{index}.err').open('w') as e:
  monitor=subprocess.Popen(['nvidia-smi','-i',uuid,'--query-gpu=timestamp,uuid,temperature.gpu,power.draw,power.limit,clocks.sm,clocks.mem,utilization.gpu,memory.used','--format=csv','-lms','500'],stdout=t,stderr=subprocess.DEVNULL)
  try:r=subprocess.run([str(base/'bench')],env=env,stdout=f,stderr=e,timeout=240)
  finally:monitor.terminate();monitor.wait()
 if r.returncode:raise SystemExit(f'GPU {index} failed exit {r.returncode}; see logs')
 data=[l for l in (out/f'gpu{index}.csv').read_text().splitlines() if not l.startswith('#')]
 records=list(csv.DictReader(data))
 for mode in ('fp32','tf32','fp16_fp32','bf16_fp32','fp16_fp16'):
  for n in ('4096','8192'):
   values=[float(x['tflops']) for x in records if x['kind']=='perf' and x['mode']==mode and x['n']==n]
   rows.append(dict(gpu=index,uuid=uuid,pci=bus,mode=mode,n=n,median_tflops=statistics.median(values),min_tflops=min(values),max_tflops=max(values)))
 print('GPU',index,'completed',flush=True)
with (out/'summary.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
(out/'health-after.txt').write_text(capture(['nvidia-smi']))
print('RESULTS='+str(out),flush=True)
