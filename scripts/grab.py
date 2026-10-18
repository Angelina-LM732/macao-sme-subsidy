# Extract the most recent browser tool result containing a marker from the session transcript
import json, sys
path='/root/.claude/projects/-home-claude/b29a18c2-c466-5b9a-ad88-c494f5eb56b8.jsonl'
marker, out = sys.argv[1], sys.argv[2]
found=None
for line in open(path):
    try: o=json.loads(line)
    except: continue
    msg=o.get('message',{})
    c=msg.get('content') if isinstance(msg,dict) else None
    if not isinstance(c,list): continue
    for b in c:
        if b.get('type')!='tool_result': continue
        cc=b.get('content')
        texts=[]
        if isinstance(cc,str): texts=[cc]
        elif isinstance(cc,list): texts=[x.get('text','') for x in cc if isinstance(x,dict)]
        for t in texts:
            if marker in t: found=t
if not found: sys.exit('not found')
# browser JS results are JSON strings
s=found
i=s.find('"'); j=s.rfind('"\n')
if j<0: j=s.rfind('"')
val=json.loads(s[i:j+1])
open(out,'w').write(val)
print(len(val.splitlines()),'lines ->',out)
