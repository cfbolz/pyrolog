import re, subprocess, collections, json
import sys
root=sys.argv[1].rstrip('/') + '/'
rows=[]
for name in ['nrev','meta_nrev']:
 for version in ['before','after']:
  prefix=root+name+'-'+version
  log=open(prefix+'.jit.log').read()
  ranges=[]
  for chunk in re.findall(r'\{jit-backend-addr\n(.*?)\n\[[^\n]+ jit-backend-addr\}',log,re.S):
   title=chunk.splitlines()[0].split(' has address')[0]
   if title.startswith('Loop '):
    start=int(re.search('function: 0x([0-9a-f]+)',chunk).group(1),16)
   else:
    start=int(re.search('jump target: 0x([0-9a-f]+)',chunk).group(1),16)
   end=int(re.search('end: 0x([0-9a-f]+)',chunk).group(1),16)
   ranges.append((start,end,title))
  script=subprocess.check_output(['perf','script','-i',prefix+'.perf.data','-F','period,ip,sym,dso'])
  with open(prefix+'.perf.txt','w') as f:f.write(script)
  report=subprocess.check_output(['perf','report','-i',prefix+'.perf.data','--stdio','--no-children','--sort','dso,symbol','--percent-limit','0.1'])
  with open(prefix+'.report.txt','w') as f:f.write(report)
  cats=collections.Counter(); symbols=collections.Counter()
  for line in script.splitlines():
   m=re.match(r'\s*(\d+)\s+([0-9a-f]+)\s+(.*?)\s+\((.*)\)$',line)
   assert m,line
   period,ip,sym,dso=m.groups();period=int(period);ip=int(ip,16)
   cat='other'
   for start,end,title in ranges:
    if start<=ip<end:
     cat='JIT';sym=title;break
   else:
    if re.search(r'^pypy_g_(trace__gc_callback|IncrementalMiniMarkGC|ArenaCollection)',sym):cat='GC'
    elif 'memmove' in sym or 'memcpy' in sym:cat='memory copy'
   cats[cat]+=period;symbols[sym]+=period
  total=sum(cats.values())
  row=dict(benchmark=name,version=version,total_period=total,categories=dict((k,100.*v/total) for k,v in cats.items()),symbols=symbols.most_common())
  rows.append(row)
  print(name,version,row['categories'])
with open(root+'perf-summary.json','w') as f:json.dump(rows,f,indent=2,sort_keys=True,separators=(',', ': '))
