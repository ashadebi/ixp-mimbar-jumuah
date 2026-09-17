with open('server.py', 'r') as f:
    content = f.read()

func = '''def assign_peer_port(asn, d):
    sw=query('SELECT id FROM switches WHERE id=?',(int(d.get('switch_id')),),one=True)
    if not sw: raise Problem('Switch tidak ditemukan.',404)
    if not 1<=asn<=4294967295: raise Problem('ASN tidak valid.')
    vals=[str(d.get(k,'')).strip() for k in ('port_number','type','status','bandwidth')]
    if any(not v or len(v)>80 for v in vals): raise Problem('Data port tidak valid.')
    
    existing = query('SELECT id FROM ports WHERE member_asn=?', (asn,), one=True)
    if existing:
        query('UPDATE ports SET switch_id=?, port_number=?, type=?, status=?, bandwidth=? WHERE id=?', (sw['id'], *vals, existing['id']))
        pid = existing['id']
    else:
        pid = query('INSERT INTO ports(switch_id,member_asn,port_number,type,status,bandwidth) VALUES(?,?,?,?,?,?)', (sw['id'], asn, *vals))
    return {'id': pid, 'port_number': vals[0]}

def infer_vendor_model(text):'''

content = content.replace('def infer_vendor_model(text):', func)

with open('server.py', 'w') as f:
    f.write(content)
