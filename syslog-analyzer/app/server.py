
import os, json, time, socketserver, threading, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .parser import parse
from .detector import detect
from .oui import OuiDB
from .store import Store
from .correlation import correlate
TOKEN=os.environ.get('SYSLOG_ANALYZER_TOKEN','change-me')
DATA=os.environ.get('DATA_DIR','/data')
store=Store(os.path.join(DATA,'syslog.sqlite3'))
oui=OuiDB(os.environ.get('OUI_FILE','/app/oui/oui.txt'))
RATE={}
def handle(raw,ip):
 now=time.time(); b=RATE.setdefault(ip,[]); b[:]=[x for x in b if now-x<1]
 if len(b)>200: return
 b.append(now)
 p=parse(raw,ip); p['source_ip']=ip; p['vendor']=oui.vendor(p.get('mac')) if p.get('mac') else 'Unknown'
 ev=detect(p); store.add(p,ev,correlate)
class UDP(socketserver.BaseRequestHandler):
 def handle(self): handle(self.request[0].decode('utf-8','replace'), self.client_address[0])
class TCP(socketserver.BaseRequestHandler):
 def handle(self):
  data=self.request.recv(8192).decode('utf-8','replace')
  for line in data.splitlines():
   if line.strip(): handle(line,self.client_address[0])
class API(BaseHTTPRequestHandler):
 def log_message(self,*a): pass
 def sendj(self,o,code=200):
  b=json.dumps(o,default=str).encode(); self.send_response(code); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
 def auth(self): return self.headers.get('X-Syslog-Token')==TOKEN
 def do_GET(self):
  if self.path=='/health': return self.sendj({'ok':True})
  if not self.auth(): return self.sendj({'error':'unauthorized'},401)
  parsed=urllib.parse.urlsplit(self.path)
  path=parsed.path
  params=urllib.parse.parse_qs(parsed.query)
  if path=='/summary': return self.sendj(store.summary())
  if path=='/logs':
   try: result=store.list_logs(params.get('limit',['20'])[0],params.get('offset',['0'])[0],params.get('source',[None])[0])
   except (ValueError,OverflowError): return self.sendj({'error':'Invalid limit or offset'},400)
   return self.sendj(result)
  if path=='/sources': return self.sendj({'items':store.list_sources()})
  if path=='/events': return self.sendj({'items':store.list_events()})
  return self.sendj({'error':'not found'},404)
def main():
 udp=socketserver.ThreadingUDPServer(('0.0.0.0',int(os.environ.get('SYSLOG_UDP_PORT','514'))),UDP)
 tcp=socketserver.ThreadingTCPServer(('0.0.0.0',int(os.environ.get('SYSLOG_TCP_PORT','514'))),TCP); tcp.allow_reuse_address=True
 api=ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('API_PORT','5514'))),API)
 for s in (udp,tcp,api): threading.Thread(target=s.serve_forever,daemon=True).start()
 while True: time.sleep(3600)
if __name__=='__main__': main()
