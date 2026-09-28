import json,re,csv
import sys
root=sys.argv[1].rstrip('/') + '/'
rows=[]
for line in open(root+'stat-samples.jsonl'):
 row=json.loads(line);prefix=row['prefix']
 gc=open(prefix+'.gc.log').read()
 for cat,key in [('gc-minor','minor'),('gc-collect-step','major_step'),('gc-collect-done','major')]:
  chunks=re.findall(r'\{'+cat+r'\n(.*?)\n\[[^\n]+ '+cat+r'\}',gc,re.S)
  row[key+'_count']=len(chunks)
  row[key+'_s']=sum(float(x) for chunk in chunks for x in re.findall('time taken: +([0-9.]+)',chunk))
 row['promoted_bytes']=sum(int(x) for x in re.findall('total size of surviving objects: (\d+)',gc))
 row['max_used_bytes']=max(int(x) for x in re.findall('minor collect, total memory used: (\d+)',gc))
 row['mean_ms']=sum(row['samples_ms'])/20.
 row['post_first_five_ms']=sum(row['samples_ms'][5:])/15.
 for line in open(prefix+'.stat'):
  if not line.strip() or line.startswith('#'):continue
  value,unit,event,rest=line.split(',',3)
  assert '<' not in value
  row[event]=float(value)
 rows.append(row)
with open(root+'stat-summary.json','w') as f:json.dump(rows,f,indent=2,sort_keys=True,separators=(',', ': '))
def median(a):
 a=sorted(a);return (a[(len(a)-1)//2]+a[len(a)//2])/2.
for name in ['nrev','meta_nrev']:
 print(name)
 for key in ['mean_ms','post_first_five_ms','cycles:u','instructions:u','cache-misses:u','branches:u','branch-misses:u','minor_count','minor_s','major_count','major_step_s','promoted_bytes','max_used_bytes']:
  a=median([r[key] for r in rows if r['benchmark']==name and r['version']=='before'])
  b=median([r[key] for r in rows if r['benchmark']==name and r['version']=='after'])
  print(key, a, b, 100*(b/a-1))
