
import time, os, tempfile
from app.parser import parse
from app.detector import detect
from app.oui import OuiDB
from app.store import Store
from app.correlation import norm
def test_rfc3164_parse_mac_iface():
 p=parse('<189>Sep 14 12:00:00 sw1 %LINK-3-UPDOWN: Interface Gi1/0/1 changed state to down mac 00:11:22:33:44:55','10.0.0.1')
 assert p['host']=='sw1' and p['severity']==5 and p['interface']=='Gi1/0/1' and p['mac']=='00:11:22:33:44:55'
def test_rfc5424_parse():
 p=parse('<34>1 2026-09-14T12:00:00Z sw1 app - - - LACP failure on Te1/1','1.1.1.1')
 assert p['host']=='sw1' and p['pri']==34 and p['interface']=='Te1/1'
def test_detection_categories():
 cats={e['type'] for e in detect({'message':'STP topology change loop blocking LACP port-security CRC auth fail fan power reboot mac move','host':'h'})}
 assert {'stp','lacp','mac_move','port_security','crc_errors','auth_failure','environment','reboot_config'} <= cats
def test_retention_prunes():
 d=tempfile.mkdtemp(); s=Store(os.path.join(d,'x.db'),retention=1)
 old={'ts':time.time()-99,'source_ip':'x','host':'h','pri':1,'severity':1,'interface':None,'mac':None,'vendor':'Unknown','message':'link down','raw':'link down'}
 s.add(old,detect(old),lambda p:{})
 assert s.summary()['logs']==0
def test_oui_unknown_and_known(tmp_path):
 f=tmp_path/'oui.txt'; f.write_text('00-11-22 Cisco Systems\n')
 o=OuiDB(str(f)); assert o.vendor('00:11:22:33:44:55')=='Cisco Systems'; assert o.vendor('AA:BB:CC:00:00:00')=='Unknown'
def test_norm_correlation(): assert norm('Gi1/0/1')==norm('gi-1/0/1')
