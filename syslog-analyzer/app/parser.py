import re, time, datetime
RFC3164=re.compile(r'^(?:<(?P<pri>\d{1,3})>)?(?P<ts>[A-Z][a-z]{2}\s+\d{1,2}\s+\d\d:\d\d:\d\d)\s+(?P<host>\S+)\s+(?P<msg>.*)$')
RFC5424=re.compile(r'^<(?P<pri>\d{1,3})>(?P<ver>\d+)\s+(?P<ts>\S+)\s+(?P<host>\S+)\s+(?P<app>\S+)\s+(?P<proc>\S+)\s+(?P<msgid>\S+)\s+(?:\S+\s+)?(?P<msg>.*)$')
MAC=re.compile(r'(?i)([0-9a-f]{2}(?:[:.-][0-9a-f]{2}){5}|[0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4})')
IFACE=re.compile(r'\b(Gi\d+(?:/\d+)*|Te\d+(?:/\d+)*|Fa\d+(?:/\d+)*|Eth\d+(?:/\d+)*|Po\d+|xe-\d+/\d+/\d+|ge-\d+/\d+/\d+|et-\d+/\d+/\d+|ethernet\d+|GigabitEthernet\d+(?:/\d+)*|TenGigabitEthernet\d+(?:/\d+)*)\b', re.IGNORECASE)
IFACE_FALLBACK=re.compile(r'(?i)\b(?:interface|port|if|on)\s+([A-Za-z]+[0-9]+[A-Za-z0-9/_.:-]+)')
def norm_mac(m):
 s=re.sub(r'[^0-9A-Fa-f]','',m or '').upper()
 return ':'.join(s[i:i+2] for i in range(0,12,2)) if len(s)>=12 else None
def parse_ts_3164(ts, now=None):
 now=now or time.time(); y=datetime.datetime.fromtimestamp(now).year
 try: return datetime.datetime.strptime(f'{y} {ts}','%Y %b %d %H:%M:%S').timestamp()
 except Exception: return now
def parse(raw, source_ip=''):
 raw=(raw or '')[:4096].replace('\x00','')
 now=time.time(); pri=None; host=source_ip; msg=raw; ts=now
 m=RFC5424.match(raw)
 if m:
  pri=int(m.group('pri')); host=m.group('host') if m.group('host')!='-' else source_ip; msg=m.group('msg')
  try: ts=datetime.datetime.fromisoformat(m.group('ts').replace('Z','+00:00')).timestamp()
  except Exception: ts=now
 else:
  m=RFC3164.match(raw)
  if m:
   pri=int(m.group('pri') or 13); host=m.group('host'); msg=m.group('msg'); ts=parse_ts_3164(m.group('ts'), now)
 sev=pri & 7 if pri is not None else None
 mm=MAC.search(msg); im=IFACE.search(msg)
 iface=im.group(1) if im else None
 if not iface:
  im2 = IFACE_FALLBACK.search(msg)
  if im2: iface = im2.group(1)
 return {'ts':ts,'pri':pri,'severity':sev,'host':host,'message':msg[:3000],'raw':raw,'mac':norm_mac(mm.group(1)) if mm else None,'interface':iface}
