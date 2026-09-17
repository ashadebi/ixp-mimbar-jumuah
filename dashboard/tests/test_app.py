import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import threading
import unittest
import yaml
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('mimbar',ROOT/'server.py')
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)

class ApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        app.DATA=Path(cls.tmp.name);app.DB=app.DATA/'test.sqlite3';app.init()
        os.environ['MIMBAR_SETUP_TOKEN']='test-bootstrap-secret'
        os.environ['MIMBAR_ALLOW_DEPLOY']='0'
        cls.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        cls.port=cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever,daemon=True).start()
        cls.cookie='';cls.csrf=''
        status,result,headers=cls.request('/setup','POST',{'name':'tester','password':'test-password-12345','setup_token':'test-bootstrap-secret'})
        assert status==200,result
        cls.cookie=headers['Set-Cookie'].split(';')[0];cls.csrf=result['csrf']
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.tmp.cleanup()
    @classmethod
    def request(cls,path,method='GET',body=None,auth=True,csrf=True,origin=None):
        c=http.client.HTTPConnection('127.0.0.1',cls.port)
        headers={'Content-Type':'application/json'}
        if auth:headers['Cookie']=cls.cookie
        if csrf:headers['X-CSRF-Token']=cls.csrf
        if origin:headers['Origin']=origin
        c.request(method,'/api'+path,json.dumps(body) if body is not None else None,headers)
        r=c.getresponse();raw=r.read();c.close()
        return r.status,json.loads(raw),dict(r.headers)

    @classmethod
    def raw_request(cls,path,method='GET',body=None,auth=True,csrf=True):
        c=http.client.HTTPConnection('127.0.0.1',cls.port)
        headers={}
        if body is not None: headers['Content-Type']='application/json'
        if auth:headers['Cookie']=cls.cookie
        if csrf:headers['X-CSRF-Token']=cls.csrf
        c.request(method,path,json.dumps(body) if body is not None else None,headers)
        r=c.getresponse();raw=r.read();c.close()
        return r.status,raw,dict(r.headers)

    def test_iixji_members_crud(self):
        # 1. POST
        payload = {
            'asn': 12345,
            'name': 'Test ISP',
            'type': 'Lokal Jatim',
            'status': 'Aktif',
            'contact': 'admin@testisp.net',
            'notes': 'Test notes'
        }
        status, data, _ = self.request('/iixji-members', 'POST', payload)
        self.assertEqual(status, 201)
        self.assertTrue(data.get('success'))
        mem_id = data.get('id')
        self.assertIsNotNone(mem_id)

        # 2. GET
        status, data, _ = self.request('/iixji-members', 'GET')
        self.assertEqual(status, 200)
        found = False
        for m in data:
            if m['id'] == mem_id:
                found = True
                self.assertEqual(m['asn'], 12345)
                self.assertEqual(m['name'], 'Test ISP')
        self.assertTrue(found)

        # 3. PUT
        update_payload = {'name': 'Updated ISP', 'status': 'Melapor'}
        status, data, _ = self.request(f'/iixji-members/{mem_id}', 'PUT', update_payload)
        self.assertEqual(status, 200)

        status, data, _ = self.request('/iixji-members', 'GET')
        m = next(x for x in data if x['id'] == mem_id)
        self.assertEqual(m['name'], 'Updated ISP')
        self.assertEqual(m['status'], 'Melapor')
        self.assertEqual(m['asn'], 12345)

        # 4. DELETE
        status, data, _ = self.request(f'/iixji-members/{mem_id}', 'DELETE')
        self.assertEqual(status, 200)

        status, data, _ = self.request('/iixji-members', 'GET')
        self.assertFalse(any(x['id'] == mem_id for x in data))

    def test_public_member_baru_submission_creates_dns_challenge(self):
        status,page,headers=self.raw_request('/member-baru',auth=False)
        self.assertEqual(status,200)
        self.assertIn(b'Member Baru',page)
        self.assertIn(b'/member-baru.js',page)
        self.assertNotIn(b'<script>f.onsubmit',page)
        status,script,_=self.raw_request('/member-baru.js',auth=False)
        self.assertEqual(status,200);self.assertIn(b'addEventListener',script)
        payload={'asn':64555,'organization':'Example Net','email':'noc@example.net','location':'AG','peering_ipv4':'103.19.76.250','peering_ipv6':'2001:db8::250','ipv4_prefixes':'198.51.100.0/24','ipv6_prefixes':'2001:db8:250::/48','bandwidth':'10G','domain':'example.net'}
        status,data,_=self.request('/member-applications','POST',payload,auth=False,csrf=False)
        self.assertEqual(status,201)
        self.assertRegex(data['pairing_code'],r'^mimbar-[a-f0-9]{24}$')
        self.assertEqual(data['txt_name'],'_arouteserver-pairing.example.net')
        row=app.query('SELECT * FROM member_applications WHERE id=?',(data['id'],),one=True)
        self.assertEqual(row['asn'],64555)
        self.assertEqual(row['pairing_verified'],0)

    def test_public_member_rejects_free_emails(self):
        payload={'asn':64555,'organization':'Example Net','email':'noc@gmail.com','location':'AG','peering_ipv4':'103.19.76.250','peering_ipv6':'2001:db8::250','ipv4_prefixes':'198.51.100.0/24','ipv6_prefixes':'2001:db8:250::/48','bandwidth':'10G','domain':'example.net'}
        status,data,_=self.request('/member-applications','POST',payload,auth=False,csrf=False)
        self.assertEqual(status,400)
        self.assertIn('Domain email tidak diizinkan', data.get('error', ''))
        
        payload['email']='admin@yahoo.com'
        status,data,_=self.request('/member-applications','POST',payload,auth=False,csrf=False)
        self.assertEqual(status,400)


    @patch('smtplib.SMTP')
    def test_public_member_sends_smtp_email_and_saves_telegram_code(self, mock_smtp):
        import os
        os.environ['MIMBAR_SMTP_HOST'] = 'smtp.example.com'
        os.environ['MIMBAR_SMTP_PORT'] = '587'
        os.environ['MIMBAR_SMTP_FROM'] = 'bot@example.com'
        
        payload={'asn':64556,'organization':'Example Net 2','email':'noc@official.net','location':'AG','peering_ipv4':'103.19.76.251','peering_ipv6':'2001:db8::251','ipv4_prefixes':'198.51.101.0/24','ipv6_prefixes':'2001:db8:251::/48','bandwidth':'10G','domain':'official.net'}
        status,data,_=self.request('/member-applications','POST',payload,auth=False,csrf=False)
        self.assertEqual(status, 201)
        row = app.query('SELECT telegram_code FROM member_applications WHERE id=?', (data['id'],), one=True)
        self.assertIsNotNone(row['telegram_code'])
        self.assertTrue(mock_smtp.called)
        
        del os.environ['MIMBAR_SMTP_HOST']

    def test_authenticated_admin_verifies_pairing_txt(self):
        app_id=app.create_member_application({'asn':64556,'organization':'Verify Net','email':'noc@verify.example','location':'AG','peering_ipv4':'103.19.76.251','peering_ipv6':'','ipv4_prefixes':'203.0.113.0/24','ipv6_prefixes':'','bandwidth':'1G','domain':'verify.example'})['id']
        code=app.query('SELECT pairing_code FROM member_applications WHERE id=?',(app_id,),one=True)['pairing_code']
        with patch.object(app,'lookup_txt',return_value=['wrong',code]):
            status,data,_=self.request('/member-applications/'+app_id+'/verify-pairing','POST',{})
        self.assertEqual(status,200)
        self.assertTrue(data['pairing_verified'])
        self.assertEqual(app.query('SELECT pairing_verified FROM member_applications WHERE id=?',(app_id,),one=True)['pairing_verified'],1)

    def test_switch_ports_and_snmp_discovery_redact_community(self):
        status,node,_=self.request('/nodes','POST',{'location':'AG','name':'Node AG 1'})
        self.assertEqual(status,201)
        status,data,_=self.request('/switches','POST',{'node_id':node['id'],'name':'Core SW','ip':'192.0.2.10','community':'secret-community'})
        self.assertEqual(status,201)
        sw=data['id']
        status,port,_=self.request('/ports','POST',{'switch_id':sw,'member_asn':64555,'port_number':'xe-0/0/1','type':'10G-LR','status':'up','bandwidth':'10G','mac_address':'aa:bb:cc:dd:ee:ff'})
        self.assertEqual(status,201)
        self.assertEqual(port.get('mac_address'),'aa:bb:cc:dd:ee:ff')
        switches=self.request('/switches')[1]
        switches_with_port=next(s for s in switches if s['id']==sw)
        p = next(p for p in switches_with_port['ports'] if p['port_number']=='xe-0/0/1')
        self.assertEqual(p['port_number'],'xe-0/0/1')
        self.assertEqual(p.get('mac_address'),'aa:bb:cc:dd:ee:ff')
        with patch.object(app,'run',return_value='SNMPv2-MIB::sysDescr.0 = STRING: Juniper Networks EX4300\nSNMPv2-MIB::sysName.0 = STRING: core1') as r:
            status,disc,_=self.request('/switches/'+str(sw)+'/discover','POST',{})
        self.assertEqual(status,200)
        self.assertEqual(disc['vendor'],'Juniper')
        self.assertIn('EX4300',disc['model'])
        self.assertNotIn('secret-community',json.dumps(disc))
        self.assertNotIn('secret-community',' '.join(r.call_args[0][0]))

    def test_switch_hierarchy_and_discovery(self):
        status, node, _ = self.request('/nodes', 'POST', {'location': 'AG', 'name': 'Node A'})
        self.assertEqual(status, 201)
        node_id = node['id']
        status, data, _ = self.request('/switches', 'POST', {'location': 'AG', 'name': 'Bad SW', 'ip': '192.0.2.20', 'community': 'pub'})
        self.assertEqual(status, 400)
        status, data, _ = self.request('/switches', 'POST', {'location': 'AG', 'node_id': node_id, 'name': 'New Core', 'ip': '192.0.2.10', 'community': 'secret', 'type': 'hacker', 'vendor': 'hacker', 'model': 'hacker'})
        self.assertEqual(status, 201)
        sw_id = data['id']
        status, switches, _ = self.request('/switches')
        sw = next(s for s in switches if s['id'] == sw_id)
        self.assertEqual(sw['node_id'], node_id)
        self.assertNotEqual(sw.get('vendor'), 'hacker')
        self.assertNotEqual(sw.get('model'), 'hacker')
        with patch.object(app, 'run', return_value='SNMPv2-MIB::sysDescr.0 = STRING: Juniper Networks EX4300\nSNMPv2-MIB::sysName.0 = STRING: core1') as r:
            status, disc, _ = self.request('/switches/'+str(sw_id)+'/discover', 'POST', {})
        self.assertEqual(status, 200)
        self.assertEqual(disc['vendor'], 'Juniper')
        with patch.object(app, 'run', side_effect=app.Problem('Timeout: No Response from 192.0.2.10', 400)) as r:
            status, err, _ = self.request('/switches/'+str(sw_id)+'/discover', 'POST', {})
        self.assertEqual(status, 400)
        self.assertIn('No Response', err['error'])

    def test_nodes_crud(self):
        status, node, _ = self.request('/nodes', 'POST', {'location': 'SUB', 'name': 'Rack 1'})
        self.assertEqual(status, 201)
        node_id = node['id']
        status, nodes, _ = self.request('/nodes')
        self.assertEqual(status, 200)
        self.assertTrue(any(n['id'] == node_id and n['name'] == 'Rack 1' for n in nodes))
        status, _, _ = self.request(f'/nodes/{node_id}', 'DELETE')
        self.assertEqual(status, 200)

    def test_peers_include_inventory_hover_fields(self):
        node=app.query('INSERT INTO nodes(location,name) VALUES(?,?)',('AG','Core Node'))
        sw=app.query('INSERT INTO switches(node_id,name,ip,community,vendor,model) VALUES(?,?,?,?,?,?)',(node,'Core','192.0.2.11','sec','Vendor','Model'))
        app.query('INSERT INTO ports(switch_id,member_asn,port_number,type,status,bandwidth) VALUES(?,?,?,?,?,?)',(sw,65001,'1/1','100G','up','100G'))
        loc=app.get_location('AG');g,c=app.parsed(loc['general'],loc['clients']);c['clients'].append({'asn':65001,'ip':'192.0.2.44','description':'Hover Net'})
        app.query('UPDATE locations SET clients=? WHERE code=?',(yaml.safe_dump(c,sort_keys=False),'AG'))
        peers=self.request('/locations/AG')[1]['peers']
        peer=next(p for p in peers if p['asn']==65001)
        self.assertEqual(peer['bandwidth'],'100G')
        self.assertEqual(peer['switch'],'Core')
        self.assertEqual(peer['port'],'1/1')

    def test_authentication_required(self):
        self.assertEqual(self.request('/state',auth=False)[0],401)
        self.assertEqual(self.request('/members',auth=False)[0],401)
        self.assertEqual(self.request('/members/0123456789/review','POST',{},csrf=False)[0],403)
    def test_bad_login_and_repeat_setup(self):
        self.assertEqual(self.request('/login','POST',{'name':'tester','password':'wrong'})[0],401)
        self.assertEqual(self.request('/setup','POST',{'name':'second','password':'another-password'})[0],409)
    def test_session_cookie_flags(self):
        status,data,headers=self.request('/login','POST',{'name':'tester','password':'test-password-12345'})
        self.assertEqual(status,200);self.assertIn('HttpOnly',headers['Set-Cookie']);self.assertIn('SameSite=Strict',headers['Set-Cookie'])
    def test_csrf_and_origin(self):
        self.assertEqual(self.request('/locations','POST',{'code':'BAD','name':'blocked'},csrf=False)[0],403)
        self.assertEqual(self.request('/locations','POST',{'code':'BAD','name':'blocked'},origin='https://evil.example')[0],403)
    def test_imported_inventory_counts(self):
        status,data,_=self.request('/state');self.assertEqual(status,200)
        locations={l['code']:l for l in data['locations']}
        self.assertEqual(locations['SUB']['peers'],206);self.assertEqual(locations['AG']['peers'],36)
        self.assertEqual(locations['SUB']['custom_peers'],38)
        self.assertEqual(len(data['machines']),3)
        self.assertTrue(all(m['status']=='unverified' for m in data['machines']))
    def test_create_location_empty_and_no_path_traversal(self):
        self.assertEqual(self.request('/locations','POST',{'code':'../BAD','name':'Invalid'})[0],400)
        self.assertEqual(self.request('/locations','POST',{'code':'ML','name':'Malang'})[0],201)
        _,loc,_=self.request('/locations/ML');self.assertEqual(loc['peers'],[])
    def test_revision_conflict_and_duplicate_peer(self):
        _,loc,_=self.request('/locations/AG')
        payload={k:loc[k] for k in ['general','clients','revision']}
        self.assertEqual(self.request('/locations/AG','PUT',payload)[0],200)
        self.assertEqual(self.request('/locations/AG','PUT',payload)[0],409)
        payload['revision']+=1
        payload['clients']='clients:\n- {asn: 64501, ip: 192.0.2.2}\n- {asn: 64502, ip: 192.0.2.2}'
        self.assertEqual(self.request('/locations/AG','PUT',payload)[0],400)
    def test_machine_validation(self):
        payload={'location':'AG','name':'Injected','host':'127.0.0.1;id','router_id':'1.2.3.4','ssh_user':'root'}
        self.assertEqual(self.request('/machines','POST',payload)[0],400)
    def test_deployment_frontend_has_history_rollback_and_no_inline_handlers(self):
        js=(ROOT/'dist'/'app.js').read_text()
        self.assertIn('Riwayat konfigurasi terpasang',js);self.assertIn('data-version-detail',js);self.assertIn('data-version-rollback',js)
        self.assertNotRegex(js,r'\s(?:onclick|onchange|onsubmit)\s*=')

    def test_snapshot_is_immutable_atomic_and_scoped(self):
        version=app.save_deployment_snapshot('sub-rs3','SUB','bird config\n','deploy','job123','tester')
        self.assertRegex(version['id'],r'^[0-9]{8}T[0-9]{6}Z-[a-f0-9]{12}$')
        self.assertEqual(app.list_deployment_versions('sub-rs3','SUB')[0]['sha256'],hashlib.sha256(b'bird config\n').hexdigest())
        self.assertEqual(app.get_deployment_version('sub-rs3','SUB',version['id'])['config'],'bird config\n')
        with self.assertRaises(app.Problem):app.get_deployment_version('../escape','SUB',version['id'])
        with self.assertRaises(FileExistsError):app._atomic_immutable_write(Path(version['config_path']),b'replaced')

    def test_history_details_diff_and_machine_location_isolation(self):
        old=app.save_deployment_snapshot('sub-rs3','SUB','old\n','deploy','one','tester')
        new=app.save_deployment_snapshot('sub-rs3','SUB','new\n','deploy','two','tester')
        app.save_deployment_snapshot('ag-rs1','AG','secret\n','deploy','three','tester')
        status,rows,_=self.request('/machines/sub-rs3/deployments')
        self.assertEqual(status,200);self.assertEqual(len(rows),2)
        status,detail,_=self.request('/machines/sub-rs3/deployments/'+old['id'])
        self.assertEqual(status,200);self.assertIn('-new',detail['diff']);self.assertIn('+old',detail['diff']);self.assertNotIn('secret',detail['diff'])

    def test_rollback_snapshots_current_before_remote_apply_and_audits(self):
        target=app.save_deployment_snapshot('sub-rs3','SUB','target\n','deploy','one','tester')
        app.save_deployment_snapshot('sub-rs3','SUB','current\n','deploy','two','tester')
        app.query("UPDATE machines SET status='reachable',bird_version=?,checked_at=? WHERE id='sub-rs3'",(app.VERSION,app.time.time()))
        calls=[]
        class Immediate:
            def submit(self,fn,*args):fn(*args)
        def fake_run(args,**kw):calls.append(json.loads(kw['input']));return json.dumps({'status':'deployed'})
        with patch.dict(os.environ,{'MIMBAR_ALLOW_DEPLOY':'1'}),patch.object(app,'ssh_args',return_value=['ssh']),patch.object(app,'run',side_effect=fake_run),patch.object(app,'POOL',Immediate()):
            status,result,_=self.request('/machines/sub-rs3/deployments/'+target['id']+'/rollback','POST',{'confirmation':'RS3 Surabaya'})
        self.assertEqual(status,202);self.assertEqual(calls[0]['config'],'target\n')
        rows=app.list_deployment_versions('sub-rs3','SUB')
        self.assertTrue(any(x['reason']=='rollback_backup' and app.get_deployment_version('sub-rs3','SUB',x['id'])['config']=='current\n' for x in rows))
        self.assertTrue(any(e['kind']=='rollback' for e in app.query('SELECT * FROM events')))

    def test_deploy_cannot_bypass_validation(self):
        config='router id 192.0.2.1;';digest=hashlib.sha256(config.encode()).hexdigest()
        app.query('INSERT INTO jobs(id,machine,location,revision,machine_revision,status,created,config,sha256) VALUES(?,?,?,?,?,?,?,?,?)',('a'*32,'sub-rs3','SUB',1,1,'generated',0,config,digest))
        with patch.dict(os.environ,{'MIMBAR_ALLOW_DEPLOY':'1'}):
            status,data,_=self.request('/jobs/'+'a'*32+'/deploy','POST',{'confirmation':'RS3 Surabaya'})
        self.assertEqual(status,409);self.assertIn('validasi',data['error'])
    def test_disabled_validator_never_marks_success(self):
        config='router id 192.0.2.1;';digest=hashlib.sha256(config.encode()).hexdigest()
        app.query('INSERT INTO jobs(id,machine,location,revision,machine_revision,status,created,config,sha256) VALUES(?,?,?,?,?,?,?,?,?)',('b'*32,'sub-rs3','SUB',1,1,'generated',0,config,digest))
        with patch.dict(os.environ,{'MIMBAR_VALIDATOR':'disabled'}):app.validate_job('b'*32,'tester')
        j=app.get_job('b'*32);self.assertEqual(j['status'],'validation_failed');self.assertIsNone(j['validated_sha'])
    def test_multiple_super_admin_sessions_and_audit(self):
        saved_cookie,saved_csrf=self.__class__.cookie,self.__class__.csrf
        accounts={}
        try:
            for name,code in [('agoes','QA'),('nurdin','QB'),('umam','QC')]:
                app.create_super_admin(name,'isolated-test-password-'+name)
                status,data,headers=self.request('/login','POST',{'name':name,'password':'isolated-test-password-'+name})
                self.assertEqual(status,200);self.assertEqual(data['role'],'super-admin')
                self.__class__.cookie=headers['Set-Cookie'].split(';')[0];self.__class__.csrf=data['csrf']
                accounts[name]=(self.__class__.cookie,self.__class__.csrf)
                status,session,_=self.request('/session');self.assertEqual(session['user'],name)
                self.assertEqual(session['role'],'super-admin')
                self.assertEqual(self.request('/locations','POST',{'code':code,'name':'Test '+name})[0],201)
                self.assertEqual(app.query('SELECT actor FROM events ORDER BY id DESC LIMIT 1',one=True)['actor'],name)
            self.assertEqual(self.request('/login','POST',{'name':'agoes','password':'isolated-test-password-umam'})[0],401)
            self.assertEqual(self.request('/setup','POST',{'name':'unregistered','password':'test-password-123'})[0],409)
            self.request('/logout','POST',{})
            self.assertEqual(self.request('/state')[0],401)
            self.__class__.cookie,self.__class__.csrf=accounts['agoes']
            self.assertEqual(self.request('/session')[1]['user'],'agoes')
        finally:self.__class__.cookie,self.__class__.csrf=saved_cookie,saved_csrf

    def test_account_schema_migration(self):
        original=app.DB
        try:
            with tempfile.TemporaryDirectory() as tmp:
                app.DB=Path(tmp)/'legacy.db'
                with app.connect() as c:
                    c.executescript("CREATE TABLE users(id INTEGER PRIMARY KEY CHECK(id=1),name TEXT NOT NULL,salt TEXT NOT NULL,password TEXT NOT NULL); CREATE TABLE sessions(token TEXT PRIMARY KEY,csrf TEXT,expires REAL);")
                    c.execute("INSERT INTO users VALUES(1,'legacy','existing-salt','existing-hash')")
                    c.execute("INSERT INTO sessions VALUES('old','csrf',99999999999)")
                app.init_accounts();app.init_accounts()
                u=app.query('SELECT * FROM users',one=True)
                self.assertEqual(u['password'],'existing-hash');self.assertEqual(u['role'],'super-admin')
                self.assertEqual(app.query('SELECT * FROM sessions'),[])
                app.create_super_admin('second','long-test-password')
                self.assertEqual(len(app.query('SELECT * FROM users')),2)
        finally:app.DB=original

    def test_source_yaml_is_schema_valid(self):
        for code in ['AG','SUB']:
            loc=app.get_location(code);g,c=app.parsed(loc['general'],loc['clients']);self.assertEqual(g['cfg']['rs_as'],7597)

    def test_templates_api(self):
        # Create a mock SOURCE directory
        with tempfile.TemporaryDirectory() as temp_source:
            mock_source = Path(temp_source)
            sub_templates_dir = mock_source / "arouteserver-sub" / "templates" / "bird"
            sub_templates_dir.mkdir(parents=True, exist_ok=True)
            template_file = sub_templates_dir / "main.j2"
            template_file.write_text("Hello {{ AS }}", encoding="utf-8")
            
            old_source = app.SOURCE
            app.SOURCE = mock_source
            try:
                status, result, headers = self.request("/locations/sub/templates", "GET")
                self.assertEqual(status, 200)
                self.assertIn("main.j2", result)
                
                status, result, headers = self.request("/locations/sub/templates/main.j2", "GET")
                self.assertEqual(status, 200)
                self.assertEqual(result.get("content"), "Hello {{ AS }}")
                
                status, result, headers = self.request("/locations/sub/templates/nope.j2", "GET")
                self.assertEqual(status, 404)
                
                status, result, headers = self.request(
                    "/locations/sub/templates/main.j2",
                    "PUT",
                    {"content": "Hello {{ AS }} updated"}
                )
                self.assertEqual(status, 200)
                self.assertEqual(template_file.read_text(encoding="utf-8"), "Hello {{ AS }} updated")
                
                status, result, headers = self.request(
                    "/locations/sub/templates/bad_name.yaml",
                    "PUT",
                    {"content": "bad"}
                )
                self.assertEqual(status, 404)
            finally:
                app.SOURCE = old_source
 
if __name__=='__main__':unittest.main(verbosity=2)