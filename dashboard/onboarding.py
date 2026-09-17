"""Durable Telegram onboarding; member input never becomes routing policy directly."""
import ipaddress
import json
import re
import secrets
import time

FIELDS = ['location', 'organization', 'asn', 'prefix4', 'prefix6', 'as_sets', 'peering4', 'peering6', 'contact', 'email']
LABELS = ['Lokasi', 'Nama jaringan', 'ASN', 'Prefix IPv4', 'Prefix IPv6', 'IRR AS-SET', 'IP peering IPv4', 'IP peering IPv6', 'Nama PIC/NOC', 'Email NOC']
PROMPTS = [
    'Pilih lokasi IXP: {locations}. Ketik kode lokasinya.',
    'Apa nama perusahaan atau jaringan Anda? (2–120 karakter)',
    'Berapa ASN publik jaringan Anda? Contoh format: AS141134.',
    'Kirim prefix IPv4 yang akan diumumkan dalam format CIDR. Pisahkan dengan spasi, koma, atau baris baru. Ketik - jika tidak ada. Ini prefix jaringan, bukan IP peering LAN.',
    'Kirim prefix IPv6 yang akan diumumkan dalam format CIDR. Ketik - jika tidak ada. Minimal satu prefix IPv4 atau IPv6 wajib diisi.',
    'Kirim nama IRR AS-SET, misalnya AS-NAMAJARINGAN atau RADB::AS-NAMAJARINGAN. Pisahkan beberapa AS-SET dengan koma. Ketik - jika tidak ada; pencarian IRR menggunakan ASN.',
    'Kirim IP peering LAN IPv4 yang sudah dialokasikan oleh IXP, tanpa /mask. Ketik - jika belum dialokasikan atau tidak digunakan. Jangan isi alamat prefix jaringan.',
    'Kirim IP peering LAN IPv6 yang sudah dialokasikan oleh IXP, tanpa /mask. Ketik - jika belum dialokasikan atau tidak digunakan.',
    'Siapa nama PIC atau tim NOC yang dapat dihubungi?',
    'Apa alamat email NOC/kontak jaringan Anda?'
]


def init_db(connect):
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS member_conversations(chat_id INTEGER PRIMARY KEY,step INTEGER NOT NULL,data TEXT NOT NULL,updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS member_requests(id TEXT PRIMARY KEY,chat_id INTEGER,user_id INTEGER,username TEXT NOT NULL DEFAULT '',data TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',created REAL NOT NULL,reviewed REAL,reviewer TEXT,reason TEXT NOT NULL DEFAULT '',revision INTEGER);
        CREATE TABLE IF NOT EXISTS telegram_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS telegram_outbox(id INTEGER PRIMARY KEY,chat_id INTEGER NOT NULL,text TEXT NOT NULL,created REAL NOT NULL,sent REAL,attempts INTEGER NOT NULL DEFAULT 0,next_try REAL NOT NULL DEFAULT 0,error TEXT);
        ''')
        columns={r[1] for r in c.execute('PRAGMA table_info(member_requests)')}
        if 'origin' not in columns:
            c.execute("ALTER TABLE member_requests ADD COLUMN origin TEXT NOT NULL DEFAULT 'telegram'")
        if 'application_id' not in columns:
            c.execute('ALTER TABLE member_requests ADD COLUMN application_id TEXT')
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS member_pending ON member_requests(chat_id) WHERE status='pending' AND chat_id IS NOT NULL")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS member_request_application ON member_requests(application_id) WHERE application_id IS NOT NULL")


def enqueue(c, chat, text):
    # Leave room below Telegram's 4096-character message limit.
    for start in range(0, len(text), 3500):
        c.execute('INSERT INTO telegram_outbox(chat_id,text,created) VALUES(?,?,?)', (chat, text[start:start+3500], time.time()))


def validate(field, text, data, locations):
    text = text.strip()
    if len(text) > 6000: raise ValueError('Isian terlalu panjang; maksimal 6000 karakter.')
    if field == 'location':
        text = text.upper()
        if text not in locations: raise ValueError('Pilih kode lokasi yang tersedia: '+', '.join(locations))
    elif field == 'asn':
        if not re.fullmatch(r'(?:AS)?[0-9]{1,10}', text, re.I): raise ValueError('ASN harus angka atau AS diikuti angka.')
        text = int(re.sub(r'^AS', '', text, flags=re.I))
        if not 1 <= text <= 4294967294 or text in (23456,65535) or 64496 <= text <= 65534 or 65536 <= text <= 65551 or text >= 4200000000:
            raise ValueError('Gunakan ASN publik; ASN private, dokumentasi, dan reserved tidak diterima.')
    elif field in ('prefix4', 'prefix6'):
        if text == '-':
            if field == 'prefix6' and not data.get('prefix4'): raise ValueError('Minimal satu prefix wajib diisi. Gunakan /kembali untuk mengisi IPv4.')
            return []
        items = re.split(r'[\s,]+', text)
        if len(items)>100: raise ValueError('Maksimal 100 prefix per keluarga IP.')
        result = []
        for item in items:
            if '/' not in item: raise ValueError('Prefix harus memakai CIDR /panjang.')
            try: net = ipaddress.ip_network(item, strict=True)
            except ValueError: raise ValueError('CIDR tidak valid atau host bit belum nol: '+item)
            if net.version != int(field[-1]) or not net.is_global or net.is_multicast or not net.network_address.is_global or not net.broadcast_address.is_global:
                raise ValueError('Gunakan prefix unicast publik IPv'+field[-1]+': '+item)
            result.append(str(net))
        return list(dict.fromkeys(result))
    elif field == 'as_sets':
        if text == '-': return []
        items = [s.upper() for s in re.split(r'[\s,]+',text)]
        if len(items)>10 or any(len(s)>160 or not re.fullmatch(r'(?:[A-Z][A-Z0-9-]*::)?(?:AS[0-9]+:)*AS-[A-Z0-9][A-Z0-9_:-]*',s) for s in items):
            raise ValueError('Format AS-SET tidak valid. Contoh: AS-NAMA atau RADB::AS123:AS-NAMA.')
        return list(dict.fromkeys(items))
    elif field in ('peering4','peering6'):
        if text == '-': return ''
        try: ip = ipaddress.ip_address(text)
        except ValueError: raise ValueError('Masukkan satu alamat IP tanpa /mask, atau - jika belum ada.')
        if ip.version != int(field[-1]) or ip.is_unspecified or ip.is_multicast or ip.is_loopback or ip.is_link_local:
            raise ValueError('Alamat peering IPv'+field[-1]+' tidak valid.')
        return str(ip)
    elif field == 'email':
        if len(text)>254 or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',text): raise ValueError('Alamat email belum valid.')
    elif not 2 <= len(text) <= 120 or any(ord(ch)<32 for ch in text):
        raise ValueError('Isi 2–120 karakter tanpa karakter kontrol.')
    return text


def display(data):
    rows=[]
    for key,label in zip(FIELDS,LABELS):
        value=data.get(key,'')
        if isinstance(value,list): value=', '.join(value)
        if key=='asn':value='AS'+str(value)
        rows.append(label+': '+str(value or 'Belum diisi / tidak digunakan'))
    return '\n'.join(rows)


class Conversation:
    def __init__(self, connect): self.connect=connect

    def handle(self, update):
        uid=update['update_id']
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            old=c.execute("SELECT value FROM telegram_meta WHERE key='offset'").fetchone()
            if old and uid<int(old['value']): return
            c.execute("INSERT OR REPLACE INTO telegram_meta VALUES('offset',?)",(str(uid+1),))
            msg=update.get('message',{})
            chat=msg.get('chat',{});who=msg.get('from',{})
            if chat.get('type')!='private' or who.get('is_bot') or chat.get('id')!=who.get('id'): return
            cid=chat['id'];text=msg.get('text','').strip()
            def reply(s): enqueue(c,cid,s)
            # Bound reply floods, including queued messages after network interruptions.
            if c.execute('SELECT COUNT(*) FROM telegram_outbox WHERE chat_id=? AND created>?',(cid,time.time()-60)).fetchone()[0]>=25:return
            locations={r['code']:r['name'] for r in c.execute('SELECT code,name FROM locations ORDER BY code DESC')}
            row=c.execute('SELECT * FROM member_conversations WHERE chat_id=?',(cid,)).fetchone()
            data=json.loads(row['data']) if row else {};step=row['step'] if row else 0
            command=text.lower().split('@')[0] if text.startswith('/') else ''
            def prompt():
                if step==len(FIELDS): return 'Tinjau pengajuan Anda:\n\n'+display(data)+'\n\nKetik KIRIM untuk menyetujui penyimpanan data ini dan mengirimnya kepada admin IXP. /kembali untuk mengoreksi; /batal untuk menghapus isian yang belum dikirim. Kepemilikan ASN/prefix masih perlu diverifikasi admin.'
                return f'[{step+1}/{len(FIELDS)}] '+PROMPTS[step].format(locations=', '.join(k+' ('+v+')' for k,v in locations.items()))
            if command in ('/bantuan','/help'):
                reply('Mimbar Jumuah Jawa Timur • Pendaftaran member IXP\n/daftar — mulai pendaftaran\n/lanjut — lanjutkan isian\n/kembali — koreksi isian sebelumnya\n/batal — hapus isian yang belum dikirim\n/status — lihat status pengajuan\nData kontak dan jaringan diteruskan ke admin IXP setelah Anda mengetik KIRIM. Jangan kirim password BGP, token, atau kunci SSH.');return
            if command.startswith('/pairing'):
                parts = text.split(maxsplit=1)
                if len(parts) < 2:
                    reply('Gunakan format: /pairing <KODE>');return
                code = parts[1].strip()
                app_row = c.execute("SELECT asn FROM member_applications WHERE telegram_code=?", (code,)).fetchone()
                if not app_row:
                    reply('Kode pairing tidak valid.');return
                asn = app_row['asn']
                count = c.execute("SELECT COUNT(*) FROM member_telegram_chats WHERE asn=?", (asn,)).fetchone()[0]
                if count >= 3:
                    reply('Batas maksimal 3 chat ID per ASN telah tercapai.');return
                try:
                    c.execute("INSERT INTO member_telegram_chats(asn, chat_id) VALUES(?, ?)", (asn, cid))
                    reply(f'Pairing berhasil. Chat ID ini dihubungkan dengan ASN {asn}.')
                except Exception as e:
                    reply('Chat ini sudah dipairing dengan ASN tersebut.')
                return
            if command=='/status':
                asn_row = c.execute("SELECT asn FROM member_telegram_chats WHERE chat_id=?", (cid,)).fetchone()
                if asn_row:
                    asn = asn_row['asn']
                    ports = c.execute("SELECT switches.name AS switch_name, ports.port_number, ports.bandwidth, ports.mac_address FROM ports JOIN switches ON ports.switch_id = switches.id WHERE ports.member_asn=?", (asn,)).fetchall()
                    if ports:
                        reply('\n\n'.join(f"Switch Name: {p['switch_name']}\nPort Number: {p['port_number']}\nBandwidth: {p['bandwidth']}\nMAC Address: {p['mac_address'] or '-'}" for p in ports))
                    else:
                        reply(f"Anda terhubung dengan ASN {asn}, tetapi belum ada port.")
                else:
                    reply("Gunakan /pairing <KODE> untuk melihat status konektivitas.")
                return
            if command=='/batal':
                c.execute('DELETE FROM member_conversations WHERE chat_id=?',(cid,));reply('Isian yang belum dikirim telah dihapus. Pengajuan yang sudah dikirim tetap tercatat. /daftar untuk mulai lagi.');return
            if command in ('/start','/daftar','/lanjut'):
                pending=c.execute("SELECT id FROM member_requests WHERE chat_id=? AND status='pending'",(cid,)).fetchone()
                if pending:reply('Pengajuan #'+pending['id']+' masih ditinjau. Ketik /status untuk melihat statusnya.');return
                if not row:
                    c.execute('INSERT INTO member_conversations VALUES(?,?,?,?)',(cid,0,'{}',time.time()))
                    reply('Assalamualaikum. Selamat datang di IXP ala Mimbar Jumuah Jawa Timur. Mari mulai silaturahmi antarjaringan. Form ini meminta ASN, prefix, dan kontak NOC untuk ditinjau admin. Isian disimpan di server IXP selama proses. Ketik /batal kapan saja untuk menghapus isian yang belum dikirim.')
                reply(prompt());return
            if not row:reply('Ketik /daftar untuk mendaftar sebagai member IXP, atau /status untuk melihat pengajuan.');return
            if command=='/kembali':
                step=max(0,step-1)
                for key in FIELDS[step:]:data.pop(key,None)
            elif step==len(FIELDS):
                if text.upper()!='KIRIM':reply(prompt());return
                rid=secrets.token_hex(5)
                c.execute('INSERT INTO member_requests(id,chat_id,user_id,username,data,created) VALUES(?,?,?,?,?,?)',(rid,cid,who['id'],who.get('username',''),json.dumps(data),time.time()))
                c.execute('DELETE FROM member_conversations WHERE chat_id=?',(cid,))
                c.execute('INSERT INTO events(at,kind,detail,actor) VALUES(?,?,?,?)',(time.time(),'member','Pengajuan #'+rid+' / '+data['location']+' diterima.','telegram'))
                reply('Terima kasih. Pengajuan #'+rid+' telah dikirim ke admin '+data['location']+'. ASN, prefix, dan IP peering akan ditinjau. Ini belum mengaktifkan sesi BGP. Ketik /status untuk memantau.');return
            else:
                if command:reply('Perintah tidak dikenal. Gunakan /bantuan.\n'+prompt());return
                try:data[FIELDS[step]]=validate(FIELDS[step],text,data,locations)
                except ValueError as e:reply(str(e)+'\n\n'+prompt());return
                step+=1
            c.execute('UPDATE member_conversations SET step=?,data=?,updated=? WHERE chat_id=?',(step,json.dumps(data),time.time(),cid))
            reply(prompt())


def listing(connect):
    with connect() as c:
        rows=[dict(r) for r in c.execute('SELECT * FROM member_requests ORDER BY created DESC LIMIT 200')]
        for r in rows:r['data']=json.loads(r['data'])
        meta={r['key']:r['value'] for r in c.execute("SELECT * FROM telegram_meta WHERE key IN ('username','heartbeat','last_error')")}
        meta['online']=time.time()-float(meta.get('heartbeat',0))<90
        meta['queued']=c.execute('SELECT COUNT(*) FROM telegram_outbox WHERE sent IS NULL AND attempts<10').fetchone()[0]
        meta['failed']=c.execute('SELECT COUNT(*) FROM telegram_outbox WHERE sent IS NULL AND attempts>=10').fetchone()[0]
        return {'requests':rows,'bot':meta}
