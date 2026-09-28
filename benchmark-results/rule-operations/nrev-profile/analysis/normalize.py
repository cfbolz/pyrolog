import re, difflib
import sys
root=sys.argv[1].rstrip('/') + '/'
for name in ['nrev','meta_nrev']:
    results=[]
    for version in ['before','after']:
        raw=open(root+name+'-'+version+'.jit.log').read()
        chunks=re.findall(r'\{jit-log-opt-(?:loop|bridge)\n(.*?)\n\[[^\n]+ jit-log-opt-', raw, re.S)
        lines=[]
        constants={}
        def constant(m):
            s=m.group(0)
            if s not in constants: constants[s]='CLASS_%d' % len(constants)
            return constants[s]
        for chunk in chunks:
            variables={}
            def variable(m):
                s=m.group(0)
                if s not in variables: variables[s]='v%d' % len(variables)
                return variables[s]
            lines.append(chunk.splitlines()[0].split(' : ')[0].split(' with ')[0]+'\n')
            for line in chunk.splitlines()[1:]:
                if 'debug_merge_point' in line or '--end of the loop--' in line: continue
                line=re.sub(r'^\+\d+: ', '', line)
                line=re.sub(r'(?:, )?descr=<Guard0x[0-9a-f]+>', '',line)
                line=re.sub(r'\) \[.*', ')',line)
                line=re.sub(r'TargetToken\(\d+\)', 'TargetToken',line)
                line=re.sub(r'\b\d{10,}\b', constant,line)
                line=re.sub(r'\b[pif]\d+\b|\bptr\d+\b', variable,line)
                lines.append(line+'\n')
        result=''.join(lines)
        result=re.sub(r'Guard 0x[0-9a-f]+', 'Guard',result)
        with open(root+name+'-'+version+'.normalized','w') as f: f.write(result)
        results.append(result.splitlines(True))
    with open(root+name+'.trace.diff','w') as f:
        f.writelines(difflib.unified_diff(results[0],results[1],fromfile='before',tofile='after'))
