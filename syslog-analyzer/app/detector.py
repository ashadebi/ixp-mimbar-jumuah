
import re, hashlib, time
RULES=[('link_down','link.*(down|failed)|changed state to down|is down',4,.9),('link_up','link.*up|changed state to up|is up',6,.8),('stp','spanning.tree|topology change|bpdu|blocking|loop',3,.85),('lacp','lacp|bundle|port.channel|bond',4,.8),('mac_move','mac.*(move|flap)|hostflap',3,.9),('port_security','port.security|security violation|err.?disable',2,.9),('crc_errors','crc|input error|fcs|alignment',4,.75),('auth_failure','auth.*fail|login.*fail|authentication failure',4,.85),('environment','temperature|overheat|power supply|fan|psu',2,.9),('reboot_config','reboot|reload|configured from|config.*change',5,.8)]
def detect(parsed):
 msg=(parsed.get('message') or '').lower(); out=[]
 for typ,pat,sev,conf in RULES:
  if re.search(pat,msg):
   key='|'.join([typ,parsed.get('host') or '',parsed.get('interface') or '',parsed.get('mac') or '', re.sub(r'\d+','N',msg)[:120]])
   out.append({'type':typ,'severity':sev,'confidence':conf,'dedupe_key':hashlib.sha1(key.encode()).hexdigest()})
 return out
