import json
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server as app
import onboarding as ob
from telegram_bot import flush, TelegramError

class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=app.DATA,app.DB
        app.DATA=Path(self.tmp.name);app.DB=app.DATA/'test.db';app.init()
        self.bot=ob.Conversation(app.connect);self.uid=0
    def tearDown(self):app.DATA,app.DB=self.old;self.tmp.cleanup()
    def send(self,text,chat=123):
        self.uid+=1
        update={'update_id':self.uid,'message':{'chat':{'type':'private','id':chat},'from':{'id':chat,'username':'member'},'text':text}}
        self.bot.handle(update);return update
    def submit(self):
        for s in ['/start','AG','Jaringan Pengujian','AS13335','1.1.1.0/24','2606:4700::/32','AS-CLOUDFLARE','-','-','Tim NOC','noc@example.org','KIRIM']:self.send(s)
        return app.query('SELECT * FROM member_requests',one=True)
    def test_resume_dedupe_and_no_auto_policy(self):
        update=self.send('/start');self.bot.handle(update)
        self.assertEqual(app.query('SELECT COUNT(*) AS n FROM member_conversations',one=True)['n'],1)
        self.send('AG');self.bot=ob.Conversation(app.connect);self.send('/lanjut')
        self.assertIn('nama perusahaan',app.query('SELECT text FROM telegram_outbox ORDER BY id DESC',one=True)['text'])
        self.send('/batal');self.assertFalse(app.query('SELECT * FROM member_conversations'))
    def test_input_validation(self):
        for asn in ['AS0','AS64512','AS23456','4200000000','65536','4294967295','1;id']:
            with self.assertRaises(ValueError):ob.validate('asn',asn,{},['AG'])
        for prefix in ['1.1.1.1/24','10.0.0.0/8','224.0.0.0/4','1.1.1.0','::/0']:
            with self.assertRaises(ValueError):ob.validate('prefix4',prefix,{},['AG'])
        with self.assertRaises(ValueError):ob.validate('prefix6','-',{'prefix4':[]},['AG'])
        with self.assertRaises(ValueError):ob.validate('as_sets','AS-X\n{injected}',{},['AG'])
        self.assertEqual(ob.validate('prefix4','1.1.1.0/24,1.1.1.0/24',{},['AG']),['1.1.1.0/24'])
    def test_review_atomic_draft_mapping_and_duplicate(self):
        req=self.submit();loc=app.get_location('AG');original=loc['clients']
        self.assertEqual(app.get_location('AG')['clients'],original)
        payload={'decision':'approve','verified':True,'revision':loc['revision'],'peering4':'103.19.76.250'}
        with self.assertRaises(app.Problem):app.review_member(req['id'],{**payload,'verified':False},'admin')
        with self.assertRaises(app.Problem):app.review_member(req['id'],{**payload,'revision':0},'admin')
        result=app.review_member(req['id'],payload,'admin');self.assertEqual(result['status'],'approved')
        new=app.get_location('AG');self.assertEqual(new['revision'],loc['revision']+1)
        _,clients=app.parsed(new['general'],new['clients']);peer=clients['clients'][-1]
        self.assertEqual(peer['cfg']['filtering']['irrdb']['as_sets'],['AS-CLOUDFLARE'])
        self.assertNotIn('white_list_route',str(peer));self.assertNotIn('prefixes',peer)
        with self.assertRaises(app.Problem):app.review_member(req['id'],payload,'admin')
        self.assertFalse(app.query('SELECT * FROM jobs'))
    def test_rejection_and_private_chat_isolation(self):
        req=self.submit();original=app.get_location('AG')['clients']
        self.send('/status',456)
        self.assertNotIn(req['id'],app.query('SELECT text FROM telegram_outbox WHERE chat_id=456 ORDER BY id DESC',one=True)['text'])
        app.review_member(req['id'],{'decision':'reject','reason':'Lengkapi otorisasi ASN.'},'admin')
        self.assertEqual(app.get_location('AG')['clients'],original)
        self.send('/daftar');self.assertTrue(app.query('SELECT * FROM member_conversations'))
        self.bot.handle({'update_id':999,'message':{'chat':{'type':'group','id':-1},'from':{'id':123},'text':'/start'}})
        self.assertFalse(app.query('SELECT * FROM telegram_outbox WHERE chat_id=-1'))
    def test_ip_conflict_keeps_pending(self):
        req=self.submit();loc=app.get_location('AG')
        with self.assertRaises(app.Problem):app.review_member(req['id'],{'decision':'approve','verified':True,'revision':loc['revision'],'peering4':app.peers_for(loc)[0]['ip']},'admin')
        self.assertEqual(app.query('SELECT status FROM member_requests',one=True)['status'],'pending')
    def test_outbox_retry_preserves_order(self):
        self.send('/start')
        class Broken:
            def call(self,*args,**kwargs):raise TelegramError(429,60)
        flush(Broken())
        rows=app.query('SELECT * FROM telegram_outbox ORDER BY id')
        self.assertEqual(rows[0]['attempts'],1);self.assertEqual(rows[1]['attempts'],0)
        self.assertIsNone(rows[0]['sent'])

    def test_telegram_pairing_command(self):
        pass
        with app.connect() as c:
            c.execute("CREATE TABLE IF NOT EXISTS member_telegram_chats(asn INTEGER, chat_id INTEGER, PRIMARY KEY(asn, chat_id))")
            c.execute("INSERT INTO member_applications(id,created,asn,organization,email,location,bandwidth,domain,pairing_code,telegram_code) VALUES(?,?,?,?,?,?,?,?,?,?)",
                       ('testreq1',0,64557,'Org','noc@org.net','AG','1G','org.net','pairing','123456'))
        
        # Test pairing successful
        self.send('/pairing 123456', chat=99991)
        row = app.query("SELECT * FROM member_telegram_chats WHERE asn=64557 AND chat_id=99991", one=True)
        self.assertIsNotNone(row)
        
        # Test invalid code
        self.send('/pairing 000000', chat=99992)
        
        # Test limit 3 chats
        with app.connect() as c:
            c.execute("INSERT INTO member_telegram_chats(asn,chat_id) VALUES(?,?)", (64557, 99993))
            c.execute("INSERT INTO member_telegram_chats(asn,chat_id) VALUES(?,?)", (64557, 99994))
        
        # Now we have 3 chats: 99991, 99993, 99994. Add 4th
        self.send('/pairing 123456', chat=99995)
        row = app.query("SELECT * FROM member_telegram_chats WHERE asn=64557 AND chat_id=99995", one=True)
        self.assertIsNone(row)
        
    def test_telegram_status_command(self):
        with app.connect() as c:
            c.execute("CREATE TABLE IF NOT EXISTS member_telegram_chats(asn INTEGER, chat_id INTEGER, PRIMARY KEY(asn, chat_id))")
            
            
            c.execute("INSERT OR REPLACE INTO switches(id, node_id, name, ip, community) VALUES(?,?,?,?,?)", (1, 1, 'Core SW', '192.168.1.1', 'public'))
            c.execute("INSERT OR REPLACE INTO ports(switch_id, member_asn, port_number, type, status, bandwidth, mac_address) VALUES(?,?,?,?,?,?,?)", (1, 64558, 'xe-0/0/1', '10G-LR', 'up', '10G', 'aa:bb:cc:dd:ee:ff'))
            c.execute("INSERT OR REPLACE INTO member_telegram_chats(asn, chat_id) VALUES(?,?)", (64558, 88881))
        
        # Test paired status
        self.send('/status', chat=88881)
        outbox = app.query("SELECT text FROM telegram_outbox WHERE chat_id=88881 ORDER BY id DESC LIMIT 1", one=True)['text']
        self.assertIn("Core SW", outbox)
        self.assertIn("xe-0/0/1", outbox)
        self.assertIn("aa:bb:cc:dd:ee:ff", outbox)
        
        # Test unpaired status
        self.send('/status', chat=88882)
        outbox2 = app.query("SELECT text FROM telegram_outbox WHERE chat_id=88882 ORDER BY id DESC LIMIT 1", one=True)['text']
        self.assertIn("/pairing", outbox2)
