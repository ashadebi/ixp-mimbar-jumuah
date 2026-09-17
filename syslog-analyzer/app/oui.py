
import re
class OuiDB:
 def __init__(self,path):
  self.map={}
  try:
   for line in open(path,encoding='utf-8',errors='ignore'):
    m=re.match(r'\s*([0-9A-Fa-f]{2})[-:]?([0-9A-Fa-f]{2})[-:]?([0-9A-Fa-f]{2})\s+(.+)',line)
    if m:self.map[''.join(m.group(i).upper() for i in range(1,4))]=m.group(4).strip()[:120]
  except FileNotFoundError: pass
 def vendor(self,mac):
  s=re.sub(r'[^0-9A-Fa-f]','',mac or '').upper()
  return self.map.get(s[:6],'Unknown')
