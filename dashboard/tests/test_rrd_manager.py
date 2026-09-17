import tempfile, unittest
from pathlib import Path
from unittest.mock import patch, call
import rrd_manager as r

class RRDTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); r.RRD_DIR=Path(self.tmp.name)
 def tearDown(self): self.tmp.cleanup()
 @patch('rrd_manager.subprocess.run')
 def test_rrd_retains_exactly_48_hours(self, run):
  p=r.ensure_rrd(1,2); cmd=run.call_args.args[0]
  self.assertIn('--step',cmd); self.assertIn('300',cmd)
  self.assertIn('DS:in:DERIVE:600:0:U',cmd); self.assertIn('DS:out:DERIVE:600:0:U',cmd)
  self.assertEqual([x for x in cmd if x.startswith('RRA:')],['RRA:AVERAGE:0.5:1:576'])
 @patch('rrd_manager.update_rrd')
 @patch('rrd_manager.subprocess.run')
 @patch('rrd_manager._inventory', return_value=[{'switch_id':1,'ip':'192.0.2.1','community':'secret','port_id':2,'ifindex':7}])
 def test_poll_batches_hc_oids_and_falls_back(self, inv, run, update):
  run.side_effect=[type('R',(),{'returncode':1,'stdout':'','stderr':'x'})(),type('R',(),{'returncode':0,'stdout':'OID = Counter32: 10\nOID = Counter32: 20\n','stderr':''})()]
  r.poll_snmp_once()
  self.assertEqual(run.call_count,2); self.assertEqual(run.call_args_list[0].args[0].count('secret'),1)
  self.assertIn('1.3.6.1.2.1.31.1.1.1.6.7',run.call_args_list[0].args[0]); update.assert_called_once_with(1,2,10,20)
 def test_collector_starts_once(self):
  r._collector_thread=None
  with patch('rrd_manager.threading.Thread') as t:
   t.return_value.is_alive.return_value=True
   self.assertTrue(r.start_background_collector()); self.assertFalse(r.start_background_collector())
   self.assertEqual(t.call_count,1)
