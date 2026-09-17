const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icons={grid:'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',pin:'M20 10c0 6-8 11-8 11S4 16 4 10a8 8 0 1 1 16 0 M15 10a3 3 0 1 1-6 0 3 3 0 0 1 6 0',server:'M3 3h18v7H3z M3 14h18v7H3z M6 6h.01 M6 17h.01 M10 6h8 M10 17h8',peers:'M12 4v7 M4 20v-6h16v6 M12 14v6 M9 2h6v5H9z M2 19h4v3H2z M10 19h4v3h-4z M18 19h4v3h-4z',rocket:'M12 16c5-3 8-8 8-13-5 0-10 3-13 8 M7 11l-4 1v5l5-1 M12 16l-1 5h5l1-5 M6 19l-3 3 M14 8h.01',clock:'M12 8v5l3 2 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',settings:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M9 3l1-2h4l1 2 3 2 3 1v4l-2 2 2 2v4l-3 1-3 2-1 2h-4l-1-2-3-2-3-1v-4l2-2-2-2V6l3-1z',arrow:'M5 12h14 M13 6l6 6-6 6',chevron:'M9 5l7 7-7 7',plus:'M12 5v14 M5 12h14',check:'M5 12l4 4L19 6',shield:'M12 2l8 3v7c0 5-8 10-8 10S4 17 4 12V5z M8 11l3 3 5-6',moon:'M20 15A9 9 0 0 1 9 3a9 9 0 1 0 11 12',book:'M12 5C8 2 4 3 2 4v16c4-2 7-1 10 1 3-2 6-3 10-1V4c-2-1-6-2-10 1v16',logout:'M9 3H3v18h6 M10 12h11 M16 7l5 5-5 5',search:'M16 16l5 5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',file:'M14 2H4v20h16V8z M14 2v6h6 M8 12h8 M8 16h8',download:'M12 3v12 M7 10l5 5 5-5 M3 16v5h18v-5',refresh:'M20 7V2l-4 4 M4 17v5l4-4 M20 7A9 9 0 0 0 4 5 M4 17a9 9 0 0 0 16 2',menu:'M3 5h18 M3 12h18 M3 19h18',close:'M5 5l14 14 M5 19L19 5',code:'M8 5l-6 7 6 7 M16 5l6 7-6 7 M14 3l-4 18',alert:'M12 3L2 21h20z M12 9v5 M12 18h.01',key:'M14 9a5 5 0 1 1-10 0 5 5 0 0 1 10 0 M13 12l8 8 M17 16l3-3'};
const I=n=>`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${icons[n]||icons.grid}"/></svg>`;
let session=null,state=null,view='overview',selectedLocation='SUB',locationTab='overview',detail=null,page=1,search='',family='all',selectedMachine='',selectedJob=null,deployVersions=[],poll=null;
let members=null;

async function manageSwitches(){
  const ls=await api('/switches');
  const nodes=await api('/nodes');
  
  let nodeHtml = `<div class="card mb"><div class="card-head"><h2>Daftar Node</h2><button class="btn primary small" data-action="add-node">Tambah Node</button></div><div class="table-wrap"><table><thead><tr><th>ID</th><th>Lokasi</th><th>Nama Node</th><th>Aksi</th></tr></thead><tbody>`;
  for(const n of nodes){
     nodeHtml += `<tr><td>${n.id}</td><td>${esc(n.location)}</td><td><strong>${esc(n.name)}</strong></td><td><button class="btn small" data-delete-node="${n.id}">Hapus</button></td></tr>`;
  }
  if(!nodes.length) nodeHtml += `<tr><td colspan="4">Belum ada node</td></tr>`;
  nodeHtml += `</tbody></table></div></div>`;

  let body=`<div class="card"><div class="card-head"><h2>Daftar Switch</h2><button class="btn primary small" data-action="add-switch">Tambah Switch</button></div><div class="table-wrap"><table><thead><tr><th>Node</th><th>Nama</th><th>IP Address</th><th>Vendor / Model</th><th>Aksi</th></tr></thead><tbody>`;
  for(const sw of ls){
     const node = nodes.find(n => n.id === sw.node_id);
     const nodeName = node ? esc(node.name) : '-';
     body+=`<tr><td>${nodeName}<br><div class="muted">${esc(sw.location)}</div></td><td><strong>${esc(sw.name)}</strong><br><div class="muted">${sw.sys_name?esc(sw.sys_name):''}</div></td><td>${esc(sw.ip)}</td><td>${esc(sw.vendor||'-')} / ${esc(sw.model||'-')}</td><td><button class="btn small" data-discover-switch="${sw.id}">SNMP Discover</button> <button class="btn small" data-manage-ports="${sw.id}">Ports</button></td></tr>`;
  }
  if(!ls.length) body+=`<tr><td colspan="5">Belum ada switch</td></tr>`;
  body+=`</tbody></table></div></div>`;
  $('#content').innerHTML=heading('Inventory Jaringan','Daftar Node, Switch, dan Port')+nodeHtml+body;
}
async function addNode(){
  showDialog('Tambah Node',`<div class="form-grid"><select name="location" class="field">${state.locations.map(l=>`<option value="${esc(l.code)}">${esc(l.code)}</option>`).join('')}</select><input class="field" name="name" placeholder="Nama Node (mis. Rack 1)"></div>`,async d=>{await api('/nodes','POST',d);toast('Node ditambahkan');manageSwitches()})
}
async function deleteNode(id){
  if(confirm("Hapus node ini?")) { await api('/nodes/'+id,'DELETE'); toast('Node dihapus'); manageSwitches(); }
}
async function addSwitch(){
  const nodes=await api('/nodes');
  if(!nodes.length) return toast('Buat Node terlebih dahulu.');
  showDialog('Tambah Switch',`<div class="form-grid"><select name="node_id" class="field">${nodes.map(n=>`<option value="${n.id}">${esc(n.location)} - ${esc(n.name)}</option>`).join('')}</select><input class="field" name="name" placeholder="Nama (Core 1)"><input class="field" name="ip" placeholder="IP Address"><input class="field" name="community" placeholder="SNMP Community"></div>`,async d=>{await api('/switches','POST',d);toast('Switch ditambahkan');manageSwitches()})
}
async function discoverSwitch(id){
  toast('Discovering via SNMP...');
  const res=await api('/switches/'+id+'/discover','POST',{});
  toast('Selesai. Terdeteksi: '+(res.vendor||'-')+' '+(res.model||'-'));
  manageSwitches()
}
async function managePorts(id){
  const ls=await api('/switches');
  const sw=ls.find(s=>s.id===id);
  let body=`<div class="card"><div class="card-head"><h2>Ports di ${esc(sw.name)}</h2><button class="btn primary small" data-add-port="${sw.id}">Tambah Port</button></div><div class="table-wrap"><table><thead><tr><th>Port</th><th>Type / BW</th><th>Status</th><th>ASN Member</th><th>MAC Address</th></tr></thead><tbody>`;
  for(const p of sw.ports){
     body+=`<tr><td><strong>${esc(p.port_number)}</strong><br><button class="btn small" data-port-graph="${sw.id}:${p.id}">Grafik utilisasi</button></td><td>${esc(p.type)}<br><div class="muted">${esc(p.bandwidth)}</div></td><td>${esc(p.status)}</td><td>AS${p.member_asn}</td><td>${esc(p.mac_address||"")}</td></tr>`;
  }
  if(!sw.ports.length) body+=`<tr><td colspan="4">Belum ada port</td></tr>`;
  body+=`</tbody></table></div></div>`;
  $('#content').innerHTML=heading('Inventory Port',`Port di ${esc(sw.name)}`)+body;
}
function addPort(swId){
  showDialog('Tambah Port',`<div class="form-grid"><input type="hidden" name="switch_id" value="${swId}"><input class="field" name="member_asn" placeholder="Member ASN" type="number"><input class="field" name="port_number" placeholder="Nomor Port (mis. 1/1/1)"><input class="field" name="type" placeholder="Tipe Port (mis. 10G-LR)"><input class="field" name="status" placeholder="Status"><input class="field" name="bandwidth" placeholder="Bandwidth"><input class="field" name="mac_address" placeholder="MAC Address"></div>`,async d=>{await api('/ports','POST',d);toast('Port ditambahkan');managePorts(swId)})
}

const titles={stats:'Stats & Grafik',iixji:'Daftar Member IIX-JI',switches:'Inventory Switch',members:'Pengajuan member',overview:'Ruang kendali',locations:'Lokasi jaringan',machines:'Mesin route server',peers:'Direktori peer',deploy:'Deployment',activity:'Catatan aktivitas',settings:'Pengaturan',location:'Detail lokasi'};
const statuses={pending:['Menunggu tinjauan','amber'],approved:['Diterima ke draft','green'],rejected:['Ditolak','red'],unverified:['Belum diperiksa',''],reachable:['Terhubung','green'],generating:['Membuat build','amber'],generated:['Siap divalidasi',''],validating:['Memvalidasi','amber'],validated:['Validasi lulus','green'],validation_failed:['Validasi gagal','red'],failed:['Build gagal','red'],deployed:['Diterapkan','green'],deploying:['Menerapkan','amber'],deploy_failed:['Deploy gagal','red'],interrupted:['Terhenti','amber']};
const badge=(text,color='')=>`<span class="badge ${color}">${esc(text)}</span>`;
const statusBadge=s=>badge(...(statuses[s]||[s,'']));
const date=t=>new Date(t*1000).toLocaleString('id-ID',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'});
const btn=(label,action,icon='',extra='')=>`<button class="btn ${extra}" data-action="${action}">${icon?I(icon):''}${label}</button>`;
const machineName=id=>state.machines.find(m=>m.id===id)?.name||id;
function toast(s){$('#toast').textContent=s;$('#toast').classList.add('visible');setTimeout(()=>$('#toast').classList.remove('visible'),4500)}
async function api(path,method='GET',body){const res=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json',...(session?.csrf?{'X-CSRF-Token':session.csrf}:{})},...(body!==undefined?{body:JSON.stringify(body)}:{})});const data=await res.json();if(!res.ok){if(res.status===401&&path!='/login'){session=null;clearInterval(poll);login(false)}throw Error(data.error||'Permintaan gagal.')}return data}
async function refresh(){state=await api('/state');if(view==='members')members=await api('/members')}
function brand(){return `<div class="brand"><img src="/favicon.svg" alt=""><div><div class="brand-name">MIMBAR</div><div class="brand-sub">JUMUAH JAWA TIMUR</div></div></div>`}
function login(setup){$('#app').innerHTML=`<main class="login"><section class="login-story">${brand()}<div class="login-quote"><div class="eyebrow">IXP ALA MIMBAR JUMUAH JAWA TIMUR</div><h1>Merawat koneksi.<br>Menebar <em>kebaikan.</em></h1><p>Ruang kendali route server Jawa Timur. Satu niat baik, untuk jaringan yang saling menguatkan.</p></div></section><section class="login-panel"><div class="login-form"><div class="eyebrow">ASSALAMUALAIKUM</div><h2>${setup?'Awali dengan niat baik.':'Selamat datang kembali.'}</h2><p>${setup?'Buat akun administrator untuk membuka ruang kendali jaringan.':'Masuk untuk mengelola route server dan menjaga setiap koneksi.'}</p><form id="login-form"><div><label class="label" for="username">Nama pengguna</label><input class="field" id="username" name="name" autocomplete="username" placeholder="Nama administrator" required minlength="2" maxlength="64"></div><div><label class="label" for="password">Kata sandi</label><input class="field" type="password" id="password" name="password" autocomplete="${setup?'new-password':'current-password'}" placeholder="${setup?'Minimal 12 karakter':'Masukkan kata sandi'}" required ${setup?'minlength="12"':''} maxlength="256"></div>${setup?'<div><label class="label" for="token">Token penyiapan</label><input class="field" id="token" name="setup_token" autocomplete="off" required placeholder="Token dari server dashboard"><p class="help">Tersimpan di dashboard/data/setup-token pada server.</p></div>':''}<div id="login-error" role="alert"></div><button class="btn primary" type="submit">${setup?'Buat akun & masuk':'Masuk ke ruang kendali'} ${I('arrow')}</button></form><div class="login-bottom">${I('shield')} Akses administrator · Sesi terlindungi<br>Jumat penuh berkah. Semoga setiap koneksi membawa manfaat.</div></div></section></main>`;$('#login-form').onsubmit=async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;try{session=await api(setup?'/setup':'/login','POST',Object.fromEntries(new FormData(e.target)));await refresh();shell();startPolling()}catch(err){$('#login-error').className='error';$('#login-error').textContent=err.message}finally{b.disabled=false}}}
function shell(){const nav=[['overview','grid','Ringkasan'],['switches','server','Inventory'],['iixji','users','Member IIX-JI'],['syslog','alert','Syslog Analisis'],['locations','pin','Lokasi jaringan'],['machines','server','Mesin RS'],['peers','peers','Daftar peer'],['members','book','Pengajuan member'],['deploy','rocket','Deployment'],['activity','clock','Aktivitas'],['stats','activity','Stats/Graph']];$('#app').innerHTML=`<div class="shell"><aside class="sidebar">${brand()}<div class="eyebrow">Ruang kendali</div><nav>${nav.map(([id,i,label])=>`<button class="nav ${view===id||(view==='location'&&id==='locations')?'active':''}" data-view="${id}">${I(i)}${label}${id==='machines'?`<span class="count">${state.machines.length}</span>`:''}</button>`).join('')}</nav><div class="eyebrow">Titik interkoneksi</div>${state.locations.map(l=>`<button class="side-loc" data-location="${esc(l.code)}"><b>${esc(l.code)}</b>${esc(l.name)}</button>`).join('')}<div class="side-bottom"><button class="nav ${view==='settings'?'active':''}" data-view="settings">${I('settings')}Pengaturan</button><div class="friday-note">“Sambung silaturahmi,<br>luaskan manfaat.”<span>SEMANGAT JUMAT BERKAH</span></div><div class="account"><div class="avatar">${esc(session.user.slice(0,2).toUpperCase())}</div><div><strong>${esc(session.user)}</strong><div class="small">${esc(session.role||'super-admin')}</div></div><button class="iconbtn" data-action="logout" aria-label="Keluar">${I('logout')}</button></div></div></aside><main class="workspace"><header class="topbar"><div class="row"><button class="iconbtn mobile-menu" data-action="menu" aria-label="Buka navigasi">${I('menu')}</button><div class="breadcrumbs"><span>IXP Jawa Timur</span><span>/</span><strong>${esc(titles[view])}</strong></div></div><div class="topbar-right"><span>${new Date().toLocaleDateString('id-ID',{weekday:'long',day:'numeric',month:'long',year:'numeric',timeZone:'Asia/Jakarta'})}</span>${badge('Target BIRD 2.19.2')}<button class="iconbtn" data-action="refresh" aria-label="Muat ulang">${I('refresh')}</button></div></header><div class="content" id="content"></div></main></div>`;render()}
function heading(title,sub,action='',eyebrow='IXP ALA MIMBAR JUMUAH JAWA TIMUR'){return `<div class="page-heading"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p>${sub}</p></div>${action}</div>`}
function footer(){return `<footer class="footnote"><span>Data konfigurasi dari arsip · Status live hanya setelah pemeriksaan SSH</span><span>DIRAWAT DENGAN NIAT BAIK.</span></footer>`}
function metric(label,value,foot,icon){return `<div class="card metric"><div class="metric-top">${label}<span class="metric-icon">${I(icon)}</span></div><div class="metric-value">${value}</div><div class="metric-foot">${foot}</div></div>`}
function locCard(l){const ms=state.machines.filter(m=>m.location===l.code);return `<article class="card location-card"><div class="row between"><div class="row"><span class="plate">${esc(l.code)}</span><div><h3 class="location-title">${esc(l.name)}</h3><p class="location-meta">Jawa Timur &nbsp; / &nbsp; AS${l.asn}</p></div></div>${badge('Revisi '+l.revision)}</div><div class="location-numbers"><div><b>${ms.length}</b><span>Mesin RS</span></div><div><b>${l.peers}</b><span>Sesi terkonfigurasi</span></div><div><b>${l.asns}</b><span>ASN unik</span></div></div><svg class="dist-svg" viewBox="0 0 100 6" preserveAspectRatio="none" role="img" aria-label="Distribusi sesi IPv4 dan IPv6"><rect width="${l.peers?100*l.v4/l.peers:0}" height="6" fill="#54755d"/><rect x="${l.peers?100*l.v4/l.peers:0}" width="${l.peers?100*l.v6/l.peers:0}" height="6" fill="#c8b784"/></svg><div class="dist-labels"><span>IPv4 · ${l.v4} sesi</span><span>IPv6 · ${l.v6} sesi</span></div><div class="location-footer"><span class="machine-summary">${I('server')}${ms.filter(m=>m.status==='reachable').length} / ${ms.length} mesin terverifikasi</span><button class="link" data-location="${esc(l.code)}">Kelola lokasi ${I('arrow')}</button></div></article>`}
function machineRows(ms){return ms.map(m=>`<div class="machine-row"><div class="machine-glyph">${I('server')}</div><div><h3>${esc(m.name)}</h3><p class="mono">${esc(m.host)} &nbsp; · &nbsp; ${esc(m.location)}</p></div>${statusBadge(m.status)}<button class="iconbtn" data-machine="${m.id}" aria-label="Kelola ${esc(m.name)}">${I('chevron')}</button></div>`).join('')||empty('Belum ada mesin','Tambahkan mesin RS pertama di lokasi ini.','server')}
function empty(title,text,icon='file'){return `<div class="empty">${I(icon)}<h3>${title}</h3><p>${text}</p></div>`}
function overview(){return heading('Ruang kendali jaringan','Setiap koneksi adalah amanah. Kelola dengan tenang dan terarah.',btn('Siapkan deployment','deploy','rocket','primary'))+`<section class="friday-banner"><div class="row"><div class="banner-icon">${I('moon')}</div><div><h2>Jumat berkah, jaringan penuh manfaat.</h2><p>Jaga silaturahmi antarjaringan. Hadirkan koneksi yang baik untuk sesama.</p></div></div><span class="eyebrow">NIAT BAIK · KONEKSI BAIK</span></section><section class="metrics">${metric('Lokasi jaringan',state.locations.length,'<strong>Jawa Timur</strong> · saling terhubung','pin')}${metric('Mesin route server',state.machines.length,`${state.machines.filter(m=>m.status==='reachable').length} terverifikasi melalui SSH`,'server')}${metric('Definisi sesi peer',state.locations.reduce((n,l)=>n+l.peers,0),'IPv4 + IPv6 · berdasarkan konfigurasi','peers')}${metric('Deployment berhasil',state.jobs.filter(j=>j.status==='deployed').length,'Dari 30 build terakhir','shield')}</section><div class="section-title"><h2>Titik-titik yang menghubungkan</h2><button class="link" data-action="add-location">${I('plus')} Tambah lokasi</button></div><section class="locations">${state.locations.map(locCard).join('')}</section><section class="lower-grid"><div class="card"><div class="card-head"><h2>Mesin route server</h2><button class="link" data-view="machines">Lihat semua ${I('arrow')}</button></div>${machineRows(state.machines.slice(0,4))}</div><div class="card"><div class="card-head"><h2>Perlu perhatian</h2>${badge('Kebijakan')}</div><div class="policy-row">${I('shield')}<div><h3>Validasi RPKI belum aktif</h3><p>${state.locations.filter(l=>!l.rpki).map(l=>esc(l.code)).join(', ')||'Semua lokasi sudah mengaktifkan RPKI'} · lihat kebijakan sebelum mengubahnya.</p></div></div><div class="policy-row">${I('code')}<div><h3>${state.locations.reduce((n,l)=>n+l.custom_peers,0)} sesi dalam template khusus</h3><p>Perubahan YAML tidak otomatis mengubah kebijakan literal dalam template SUB.</p></div></div><div class="policy-row">${I('check')}<div><h3>Validasi sebelum deployment</h3><p>Build wajib lolos BIRD 2.19.2 sebelum dikirim ke mesin tujuan.</p></div></div></div></section>`+footer()}
function machines(){return heading('Mesin route server','Daftarkan mesin BIRD, periksa koneksi, lalu siapkan konfigurasinya.',btn('Tambah mesin','add-machine','plus','primary'))+`<div class="card"><div class="card-head"><h2>Inventaris mesin</h2>${badge(state.machines.length+' mesin')}</div><div class="table-wrap"><table><thead><tr><th>Mesin / Alamat</th><th>Lokasi</th><th>BIRD terdeteksi</th><th>Status</th><th></th></tr></thead><tbody>${state.machines.map(m=>`<tr><td><strong>${esc(m.name)}</strong><div class="muted mono">${esc(m.host)}</div></td><td>${badge(m.location)}</td><td>${esc(m.bird_version||'Belum diperiksa')}</td><td>${statusBadge(m.status)}</td><td><button class="btn small" data-machine="${m.id}">Kelola ${I('arrow')}</button></td></tr>`).join('')}</tbody></table></div></div>`}
function locDetail(){if(!detail)return '<div class="loading-inline">Memuat lokasi…</div>';const l=state.locations.find(l=>l.code===selectedLocation);return heading(esc(l.name),`${esc(l.code)} / AS${l.asn} · ${l.peers} sesi terkonfigurasi`,btn('Tambah mesin','add-machine','plus','primary'))+`<div class="tabs">${[['overview','Ringkasan lokasi'],['peers','Daftar peer'],['config','Konfigurasi']].map(([k,v])=>`<button class="tab ${locationTab===k?'active':''}" data-tab="${k}">${v}</button>`).join('')}</div>`+(locationTab==='overview'?`<div class="metrics">${metric('Sesi IPv4',l.v4,'Konfigurasi · bukan sesi live','peers')}${metric('Sesi IPv6',l.v6,'Konfigurasi · bukan sesi live','peers')}${metric('Klien YAML',l.yaml_peers,'Dikelola melalui clients.yml','file')}${metric('Sesi khusus',l.custom_peers,'Didefinisikan dalam template','code')}</div><div class="lower-grid"><div class="card"><div class="card-head"><h2>Mesin di ${esc(l.name)}</h2></div>${machineRows(state.machines.filter(m=>m.location===l.code))}</div><div class="card"><div class="card-head"><h2>Kebijakan lokasi</h2></div><div class="card-body checks"><div class="check">RPKI origin validation ${badge(l.rpki?'Aktif':'Nonaktif',l.rpki?'green':'amber')}</div><div class="check">Penolakan prefix IRR ${badge(l.irr?'Aktif':'Nonaktif',l.irr?'green':'amber')}</div><div class="check">Path hiding ${badge(l.path_hiding?'Aktif':'Nonaktif')}</div></div></div></div>`:locationTab==='peers'?peerTable():configEditor())}
function peerTable(){if(!detail)return '<div class="loading-inline">Memuat peer…</div>';const filtered=detail.peers.filter(p=>(family==='all'||p.family===Number(family))&&`${p.asn} ${p.ip} ${p.description} ${p.source}`.toLowerCase().includes(search.toLowerCase()));const max=Math.max(1,Math.ceil(filtered.length/15));page=Math.min(page,max);return `<div class="card"><div class="card-head"><h2>Peer ${esc(selectedLocation)}</h2>${btn('Tambah peer','add-peer','plus','primary small')}</div><div class="toolbar"><div class="search">${I('search')}<input id="peer-search" class="field" placeholder="Cari ASN, nama, atau alamat IP…" value="${esc(search)}" aria-label="Cari peer"></div><select class="field" id="peer-family" aria-label="Keluarga IP"><option value="all">Semua keluarga IP</option><option value="4" ${family==='4'?'selected':''}>IPv4</option><option value="6" ${family==='6'?'selected':''}>IPv6</option></select>${view==='peers'?`<select class="field" id="peer-location" aria-label="Lokasi">${state.locations.map(l=>`<option value="${esc(l.code)}" ${l.code===selectedLocation?'selected':''}>${esc(l.code)} · ${esc(l.name)}</option>`).join('')}</select>`:''}</div><div class="table-wrap"><table><thead><tr><th>Peer / ASN</th><th>Alamat IP</th><th>AF</th><th>Sumber konfigurasi</th><th></th></tr></thead><tbody>${filtered.slice((page-1)*15,page*15).map(p=>`<tr><td title="Switch: ${p.switch||'-'}\nPort: ${p.port||'-'}\nBW: ${p.bandwidth||'-'}"><strong>AS${p.asn}</strong><div class="muted">${esc(p.description.replace(/^AS\d+\s*-?\s*/,''))}</div></td><td class="mono">${esc(p.ip)}</td><td>${badge('IPv'+p.family)}</td><td>${badge(p.source,p.source==='YAML'?'':'amber')}</td><td>${p.source==='YAML'?`<button class="iconbtn table-action" data-remove-peer="${esc(p.ip)}" aria-label="Hapus peer ${esc(p.ip)}">${I('close')}</button>`:''}<button class="iconbtn table-action" data-assign-peer="${p.asn}" title="Assign to switch">${I('server')}</button></td></tr>`).join('')||'<tr><td colspan="5">Tidak ada peer yang cocok.</td></tr>'}</tbody></table></div><div class="pagination"><span>${filtered.length} sesi · Halaman ${page} dari ${max}</span><div class="row">${btn('Sebelumnya','prev-page')}${btn('Berikutnya','next-page')}</div></div></div>`}
let editorFile='general';
function configEditor(){return `<div class="stack"><div class="row between"><p class="help">Sesuaikan kebijakan melalui formulir atau editor YAML.</p>${btn('Atur kebijakan','edit-policy','settings')}</div>${detail.source==='sub'?`<div class="notice">${I('alert')}<span>SUB memakai template khusus untuk 38 sesi tambahan. Editor ini mengubah YAML; template asli tetap disertakan saat build.</span></div>`:''}<div class="card"><div class="editor-head"><div class="row"><select class="field" id="editor-file" aria-label="Berkas konfigurasi"><option value="general" ${editorFile==='general'?'selected':''}>general.yml</option><option value="clients" ${editorFile==='clients'?'selected':''}>clients.yml</option>${(detail.templates||[]).map(t=>`<option value="${esc(t)}" ${editorFile===t?'selected':''}>${esc(t)}</option>`).join('')}</select>${badge('Draft revisi '+detail.revision)}</div>${btn('Simpan draft','save-config','check','primary small')}</div><textarea id="yaml-editor" class="editor" spellcheck="false" aria-label="Editor konfigurasi YAML">${esc(detail[editorFile])}</textarea></div><p class="help">Draft disimpan terpisah dari arsip. Router ID disesuaikan dengan mesin tujuan saat build. Simpan draft, lalu buat build baru sebelum deploy.</p></div>`}
function deployment(){if(!selectedMachine)selectedMachine=state.machines[0]?.id||'';const m=state.machines.find(m=>m.id===selectedMachine);const jobs=state.jobs.filter(j=>j.machine===selectedMachine);const j=selectedJob&&jobs.find(j=>j.id===selectedJob)||jobs[0];const busy=j&&['generating','validating','deploying'].includes(j.status);return heading('Siapkan. Periksa. Terapkan.','Satu konfigurasi yang ditinjau, untuk satu mesin tujuan.',badge('BIRD 2.19.2','green'),'DEPLOYMENT ROUTE SERVER')+`<div class="stepper"><div class="step active"><b>01</b>Pilih mesin</div><div class="step ${j?'active':''}"><b>02</b>Buat konfigurasi</div><div class="step ${j?.validated_sha?'active':''}"><b>03</b>Validasi BIRD</div><div class="step ${j?.status==='deployed'?'active':''}"><b>04</b>Deploy</div></div><div class="lower-grid"><div class="stack"><div class="card"><div class="card-head"><h2>Tujuan deployment</h2>${m?badge(m.location):''}</div><div class="card-body divider"><label class="label" for="deploy-machine">Mesin route server</label><select class="field" id="deploy-machine">${state.machines.map(x=>`<option value="${x.id}" ${x.id===selectedMachine?'selected':''}>${esc(x.name)} · ${esc(x.host)}</option>`).join('')}</select>${m?`<div class="checks"><div class="check"><div>Router ID<div class="help mono">${esc(m.router_id)}</div></div>${statusBadge(m.status)}</div><div class="check"><div>Versi pada mesin<div class="help">${esc(m.bird_version||'Belum diketahui')}</div></div>${btn('Periksa SSH','check-ssh','refresh','small')}</div></div>`:''}<div class="row wrap">${btn('Buat build baru','build','code','primary')}${btn('Pengaturan mesin','edit-machine','settings')}${m?`<button class="btn" data-location="${esc(m.location)}" data-config="true">${I('file')} Tinjau YAML</button>`:''}</div></div></div><div class="card"><div class="card-head"><h2>${j?'Build '+j.id.slice(0,8):'Hasil build'}</h2>${j?statusBadge(j.status):badge('Belum tersedia')}</div>${j?`<div class="card-body divider"><p class="help">${date(j.created)} · Revisi ${j.revision} · ${esc(machineName(j.machine))}</p><div class="row wrap job-actions"><button class="btn small" data-job-preview="${j.id}">${I('file')} Lihat konfigurasi</button><button class="btn small" data-job-download="${j.id}">${I('download')} Unduh .conf</button></div><pre class="code ${busy?'busy':''}">${esc(j.log||'Menyiapkan generator…')}</pre>${j.sha256?`<p class="help mono">SHA-256 ${j.sha256.slice(0,20)}…</p>`:''}</div>`:empty('Belum ada build untuk mesin ini','Buat konfigurasi dari draft lokasi. Hasilnya dapat ditinjau dan diunduh sebelum validasi.','code')}</div></div><div class="stack"><div class="card"><div class="card-head"><h2>Pemeriksaan kesiapan</h2>${I('shield')}</div><div class="card-body divider checks"><div class="check"><span>Generator ARouteServer</span>${badge(state.capabilities.generator?'Tersedia':'Belum terpasang',state.capabilities.generator?'green':'amber')}</div><div class="check"><span>Validator BIRD</span>${badge(state.capabilities.validator==='docker'?'Docker diaktifkan':'Belum diaktifkan',state.capabilities.validator==='docker'?'':'amber')}</div><div class="check"><span>Build tervalidasi</span>${badge(j?.status==='validated'?'Lulus':'Belum',j?.status==='validated'?'green':'')}</div><div class="check"><span>Akses deploy</span>${badge(state.capabilities.deploy_enabled?'Diaktifkan':'Belum diaktifkan',state.capabilities.deploy_enabled?'green':'')}</div><div class="stack ready-actions"><button class="btn" data-action="validate" ${!j||busy||!j.sha256||j.status==='deployed'?'disabled':''}>${I('check')} Validasi BIRD 2.19.2</button><button class="btn primary" data-action="deploy-confirm" ${j?.status!=='validated'||!state.capabilities.deploy_enabled?'disabled':''}>${I('rocket')} Tinjau & deploy</button><p class="help">ARouteServer memakai profil sintaks 2.16. Kompatibilitas wajib diperiksa dengan BIRD 2.19.2. Deploy memerlukan checksum yang sesuai dan konfirmasi mesin.</p></div></div></div><div class="card"><div class="card-head"><h2>Build sebelumnya</h2></div>${jobs.slice(0,5).map(x=>`<button class="job row between" data-select-job="${x.id}"><span class="mono">${x.id.slice(0,8)}</span>${statusBadge(x.status)}</button>`).join('')||empty('Riwayat masih kosong','Build akan tercatat di sini.','clock')}</div><div class="card"><div class="card-head"><h2>Riwayat konfigurasi terpasang</h2>${badge(deployVersions.length+' versi')}</div>${deployVersions.slice(0,8).map(v=>`<div class="job"><div class="row between"><span class="mono">${esc(v.id)}</span>${badge(esc(v.reason))}</div><p class="help mono">${esc((v.sha256||'').slice(0,20))}…</p><div class="row wrap"><button class="btn small" data-version-detail="${esc(v.id)}">${I('file')} Detail / diff</button><button class="btn small" data-version-rollback="${esc(v.id)}">${I('refresh')} Rollback</button></div></div>`).join('')||empty('Belum ada snapshot','Snapshot dibuat sebelum deploy dan rollback.','clock')}</div></div></div>`}
function activity(){return heading('Jejak setiap perubahan','Catatan penyimpanan, pemeriksaan, dan deployment yang benar-benar dijalankan.')+`<div class="card"><div class="card-head"><h2>Aktivitas terbaru</h2>${badge(state.events.length+' catatan')}</div>${state.events.map(e=>`<div class="event"><time>${date(e.at)}</time><div><p>${esc(e.detail)}</p><small>${esc(e.actor)} · ${esc(e.kind)}</small></div></div>`).join('')}</div>`}
function settings(){return heading('Fondasi ruang kendali','Lokal, terarah, dan siap bertumbuh bersama titik interkoneksi baru.')+`<div class="lower-grid"><div class="card"><div class="card-head"><h2>Lingkungan aplikasi</h2></div><div class="card-body divider checks"><div class="check">Penempatan ${badge('Self-hosted')}</div><div class="check">Target validator ${badge('BIRD 2.19.2','green')}</div><div class="check">Generator ${badge(state.capabilities.generator?'ARouteServer tersedia':'Belum tersedia',state.capabilities.generator?'green':'amber')}</div><div class="check">SSH key pada server ${badge(state.capabilities.ssh_configured?'Dikonfigurasi':'Belum diatur')}</div><div class="check">Validator ${badge(state.capabilities.validator)}</div><div class="check">Deploy ke RS ${badge(state.capabilities.deploy_enabled?'Diaktifkan':'Belum diaktifkan')}</div>${state.capabilities.snapshot_validation?.filter(x=>['ag','sub'].includes(x.case)).map(x=>`<div class="check"><span>Snapshot ${x.case.toUpperCase()} · parser 2.19.2</span>${statusBadge(x.status)}</div>`).join('')||''}</div></div><div class="stack"><div class="card"><div class="card-head"><h2>Dokumentasi</h2>${I('book')}</div><div class="card-body divider stack"><a class="link" href="https://bird.nic.cz/doc/bird-2.19.2.html" target="_blank" rel="noreferrer">Panduan resmi BIRD 2.19.2 ${I('arrow')}</a><a class="link" href="https://arouteserver.readthedocs.io/en/latest/GENERAL.html" target="_blank" rel="noreferrer">Kebijakan ARouteServer ${I('arrow')}</a><p class="help">Aktivasi validator, SSH, dan agent deployment dijelaskan di README aplikasi. Kunci privat disimpan di server, bukan di browser.</p></div></div><div class="notice">${I('shield')}<span>Tidak ada status live yang disimulasikan. Data sesi berasal dari konfigurasi; jumlah sesi Established belum dipantau.</span></div></div></div>`}

function memberPage(){if(!members)return empty('Memuat pengajuan','');const b=members.bot;const pending=members.requests.filter(r=>r.status==='pending').length;return heading('Menyambut jaringan baru','Member mengisi lewat Telegram. Anda meninjau sebelum menambahkan sesi ke draft.',badge(pending+' menunggu','amber'))+`<div class="notice">${I('book')}<span>${b.username?`Bot <a href="https://t.me/${encodeURIComponent(b.username)}" target="_blank" rel="noreferrer">@${esc(b.username)}</a> · ${b.online?'Worker berjalan':'Worker belum terhubung'}`:'Bot belum terhubung'} · Ketik /daftar di percakapan pribadi.${b.last_error?'<br>'+esc(b.last_error):''}${b.failed?'<br>'+b.failed+' pesan gagal terkirim.':''}</span></div><div class="card"><div class="card-head"><h2>Pengajuan member</h2>${btn('Muat ulang','refresh','refresh','small')}</div><div class="table-wrap"><table><thead><tr><th>Jaringan / ASN</th><th>Lokasi</th><th>Prefix</th><th>Status</th><th></th></tr></thead><tbody>${members.requests.map(r=>`<tr><td><strong>${esc(r.data.organization)}</strong><div class="muted">AS${esc(r.data.asn)} · ${date(r.created)}</div></td><td>${badge(r.data.location)}</td><td>${r.data.prefix4.length} IPv4 · ${r.data.prefix6.length} IPv6</td><td>${statusBadge(r.status)}</td><td><button class="btn small" data-member="${r.id}">${r.status==='pending'?'Tinjau':'Lihat'} ${I('arrow')}</button></td></tr>`).join('')||'<tr><td colspan="5">Belum ada pengajuan. Bagikan tautan bot kepada calon member.</td></tr>'}</tbody></table></div></div><p class="help">Prefix yang dilaporkan disimpan untuk verifikasi admin. Filter rute mengikuti kebijakan IRR/RPKI lokasi. Persetujuan tidak otomatis mengaktifkan sesi BGP.</p>`}
async function reviewMember(id){const r=members.requests.find(r=>r.id===id);const d=r.data;const loc=await api('/locations/'+d.location);const rows=[['Lokasi',d.location],['Jaringan',d.organization],['ASN','AS'+d.asn],['Prefix IPv4',d.prefix4.join(', ')||'—'],['Prefix IPv6',d.prefix6.join(', ')||'—'],['IRR AS-SET',d.as_sets.join(', ')||'Pencarian berdasarkan ASN'],['Kontak NOC',d.contact+' · '+d.email],['Telegram',r.username?'@'+r.username:'ID '+r.user_id]];const info=`<div class="member-details">${rows.map(([k,v])=>`<div><span class="label">${esc(k)}</span><div>${esc(v)}</div></div>`).join('')}</div>`;if(r.status!=='pending'){showDialog('Pengajuan #'+id,info+`<p>${statusBadge(r.status)} · ${esc(r.reason||'Tanpa catatan')}</p><p class="help">${esc(d.approved_peering4||'')} ${esc(d.approved_peering6||'')}</p>`,async()=>{});$('#modal button[type="submit"]').textContent='Tutup';return}const optional=(af)=>`<div><label class="label" for="f-peering${af}">IP peering LAN IPv${af}</label><input class="field" id="f-peering${af}" name="peering${af}" value="${esc(d['peering'+af])}" placeholder="Isi jika dialokasikan"></div>`;showDialog('Tinjau pengajuan #'+id,info+`<div class="notice">${I('shield')}<span>Verifikasi kewenangan ASN/prefix dan alokasi IP peering. Pastikan objek IRR dan ROA sesuai kebijakan lokasi. Persetujuan menambahkan sesi ke draft ${esc(d.location)} revisi ${loc.revision}.</span></div><div class="form-grid">${optional('4')}${optional('6')}<div><label class="label" for="f-community">Community lokasi</label><select id="f-community" class="field" name="community"><option value="">Tanpa tambahan</option>${loc.communities.map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join('')}</select></div><div><label class="label" for="f-decision">Keputusan</label><select class="field" id="f-decision" name="decision"><option value="approve">Terima ke draft</option><option value="reject">Tolak pengajuan</option></select></div></div><label class="toggle-row"><span>Saya telah memverifikasi ASN, prefix, dan IP peering untuk persetujuan ini.</span><input type="checkbox" name="verified"></label><label class="label" for="f-reason">Catatan untuk member (wajib jika ditolak)</label><textarea class="field" id="f-reason" name="reason" maxlength="1000" rows="3"></textarea>`,async form=>{await api('/members/'+id+'/review','POST',{...form,verified:form.verified==='on',revision:loc.revision});toast('Tinjauan disimpan. Notifikasi masuk antrean Telegram.')});$('#modal button[type="submit"]').textContent='Simpan keputusan'}

function render(){let html='';if(view==='overview')html=overview();else if(view==='locations')html=heading('Titik interkoneksi Jawa Timur','Satu ruang kendali untuk setiap lokasi dan setiap mesin.',btn('Tambah lokasi','add-location','plus','primary'))+`<div class="locations">${state.locations.map(locCard).join('')}</div>`+footer();else if(view==='machines')html=machines();else if(view==='location')html=locDetail();else if(view==='peers')html=heading('Direktori peer','Daftar sesi IPv4 dan IPv6, termasuk peer dari template khusus.')+peerTable();else if(view==='deploy')html=deployment();else if(view==='activity')html=activity();else if(view==='members')html=memberPage();else if(view==='iixji')html=iixjiPage();else if(view==='syslog'){ syslogPage().then(h => { $('#content').innerHTML=h; bindContent(); }); return; }else if(view==='switches'){ manageSwitches(); return; }else if(view==='stats'){statsPage().then(h=>{$('#content').innerHTML=h;bindContent()});return;}else html=settings();$('#content').innerHTML=html;bindContent()}
async function navigate(v){view=v;page=1;if(v==='members')members=await api('/members');if(v==='iixji')window.iixji_data=await api('/iixji-members');if(v==='peers'){detail=await api('/locations/'+selectedLocation);try{detail.templates=await api('/locations/'+selectedLocation+'/templates')}catch(e){}}shell();window.scrollTo(0,0)}
async function openLocation(code,config=false){selectedLocation=code;locationTab=config?'config':'overview';detail=await api('/locations/'+code);try{detail.templates=await api('/locations/'+code+'/templates')}catch(e){detail.templates=[]};view='location';shell();window.scrollTo(0,0)}
function showDialog(title,form,callback){const dialog=$('#modal');dialog.innerHTML=`<div class="dialog-head"><h2>${title}</h2><button class="iconbtn" data-action="close-modal" aria-label="Tutup">${I('close')}</button></div><form>${form}<div id="dialog-error" role="alert"></div><div class="dialog-actions"><button type="button" class="btn" data-action="close-modal">Batal</button><button class="btn primary" type="submit">Simpan ${I('check')}</button></div></form>`;dialog.showModal();dialog.querySelector('form').onsubmit=async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;try{await callback(Object.fromEntries(new FormData(e.target)));dialog.close();await refresh();shell()}catch(err){$('#dialog-error').className='error';$('#dialog-error').textContent=err.message}finally{b.disabled=false}}}
const field=(label,name,placeholder='',value='',attrs='')=>`<div><label class="label" for="f-${name}">${label}</label><input id="f-${name}" class="field" name="${name}" placeholder="${esc(placeholder)}" value="${esc(value)}" ${attrs} required></div>`;
function addLocation(){showDialog('Tambah titik interkoneksi',`<div class="form-grid">${field('Kode lokasi','code','Contoh: ML', '', 'pattern="[A-Za-z][A-Za-z0-9-]{1,7}" maxlength="8"')}${field('Nama kota','name','Contoh: Malang')}</div><p class="help">Lokasi baru dimulai dengan daftar peer kosong dan kebijakan dasar AG. Tinjau konfigurasinya sebelum menambahkan mesin.</p>`,async d=>{await api('/locations','POST',d);toast('Lokasi baru ditambahkan.')})}
function addMachine(){showDialog('Daftarkan mesin RS',`<div class="form-grid"><div><label class="label" for="f-location">Lokasi</label><select id="f-location" name="location" class="field">${state.locations.map(l=>`<option value="${esc(l.code)}" ${l.code===selectedLocation?'selected':''}>${esc(l.code)} · ${esc(l.name)}</option>`).join('')}</select></div>${field('Nama mesin','name','Contoh: RS1 Surabaya')}${field('Alamat IP SSH','host','10.0.0.10')}${field('Router ID (IPv4)','router_id','103.19.76.2')}${field('Pengguna SSH','ssh_user','','root')}${field('Port SSH','ssh_port','','22','type="number" min="1" max="65535"')}<div><label class="label" for="f-ssh_key">Kunci Privat SSH / Deploy Key</label><textarea id="f-ssh_key" class="field" name="ssh_key" placeholder="Opsional, jika kosong gunakan default"></textarea></div></div><p class="help">BIRD harus sudah terpasang di mesin tujuan. Kunci SSH dan known_hosts dikonfigurasi pada server dashboard.</p>`,async d=>{if(!d.ssh_key) delete d.ssh_key; await api('/machines','POST',d);toast('Mesin terdaftar. Koneksi belum diperiksa.')})}
function editMachine(){const m=state.machines.find(m=>m.id===selectedMachine);showDialog('Pengaturan mesin',`<div class="form-grid">${field('Nama mesin','name','',m.name)}${field('Alamat IP SSH','host','',m.host)}${field('Router ID (IPv4)','router_id','',m.router_id)}${field('Pengguna SSH','ssh_user','',m.ssh_user)}${field('Port SSH','ssh_port','',m.ssh_port,'type="number" min="1" max="65535"')}<div><label class="label" for="f-ssh_key">Kunci Privat SSH</label><textarea id="f-ssh_key" class="field" name="ssh_key" placeholder="Kunci Privat SSH (Kosongkan jika tidak diubah)"></textarea><p class="help">Kunci Privat SSH (Kosongkan jika tidak diubah)</p></div></div><p class="help">Perubahan membatalkan hasil pemeriksaan koneksi. Buat build baru setelah pengaturan mesin berubah.</p>`,async d=>{if(!d.ssh_key) delete d.ssh_key; await api('/machines/'+m.id,'PUT',{...d,revision:m.revision});toast('Pengaturan mesin disimpan.')})}
function addPeer(){showDialog('Tambah peer '+esc(selectedLocation),`<div class="form-grid">${field('ASN','asn','Contoh: 141134','','type="number" min="1" max="4294967295"')}${field('Nama jaringan','description','Nama operator')}${field('Alamat IPv4 atau IPv6','ip','Alamat peer pada peering LAN')}<div><label class="label" for="f-community">Community lokasi</label><select class="field" id="f-community" name="community"><option value="">Tanpa community tambahan</option>${detail.communities.map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join('')}</select></div></div><p class="help">Satu alamat IP membentuk satu sesi. Tambahkan sesi IPv4 dan IPv6 secara terpisah.</p>`,async d=>{await api('/locations/'+selectedLocation+'/peers','POST',{...d,revision:detail.revision});detail=await api('/locations/'+selectedLocation);toast('Peer ditambahkan ke draft.')})}
function removePeer(ip){showDialog('Hapus sesi peer',`<p>Sesi <b class="mono">${esc(ip)}</b> akan dihapus dari draft ${esc(selectedLocation)}.</p><p class="help">Mesin RS tidak berubah sampai build baru diterapkan.</p>`,async()=>{await api('/locations/'+selectedLocation+'/peers','POST',{remove_ip:ip,revision:detail.revision});detail=await api('/locations/'+selectedLocation);toast('Sesi dihapus dari draft.')});$('#modal button[type="submit"]').textContent='Hapus dari draft'}
function editPolicy(){const p=detail.policy;const toggle=(key,title,help)=>`<label class="toggle-row"><span><b>${title}</b><p>${help}</p></span><input type="checkbox" name="${key}" ${p[key]?'checked':''}></label>`;showDialog('Kebijakan '+esc(selectedLocation),`<div>${toggle('rpki','Validasi RPKI','Validasi origin ASN menggunakan sumber ROA yang dikonfigurasi.')}${toggle('irr_origin','Tolak origin di luar AS-SET','Origin ASN harus terdaftar dalam AS-SET klien.')}${toggle('irr_prefix','Tolak prefix di luar AS-SET','Prefix harus sesuai objek route IRR klien.')}${toggle('path_hiding','Mitigasi path hiding','Gunakan jalur alternatif yang lolos filter ekspor.')}</div><div class="form-grid">${field('IPv4 minimum','ipv4_min','',p.ipv4_min,'type="number" min="0" max="32"')}${field('IPv4 maksimum','ipv4_max','',p.ipv4_max,'type="number" min="0" max="32"')}${field('IPv6 minimum','ipv6_min','',p.ipv6_min,'type="number" min="0" max="128"')}${field('IPv6 maksimum','ipv6_max','',p.ipv6_max,'type="number" min="0" max="128"')}</div><p class="help">Perubahan berlaku pada draft YAML. Nilai literal di template khusus SUB perlu ditinjau tersendiri.</p>`,async d=>{for(const key of ['rpki','irr_origin','irr_prefix','path_hiding'])d[key]=d[key]==='on';await api('/locations/'+selectedLocation+'/policy','POST',{...d,revision:detail.revision});detail=await api('/locations/'+selectedLocation);toast('Kebijakan disimpan ke draft.')})}
function currentJob(){const jobs=state.jobs.filter(j=>j.machine===selectedMachine);return jobs.find(j=>j.id===selectedJob)||jobs[0]}

async function showDeploymentVersion(id){const v=await api('/machines/'+selectedMachine+'/deployments/'+id);const dialog=$('#modal');dialog.innerHTML=`<div class="dialog-head"><h2>Snapshot ${esc(id)}</h2><button class="iconbtn" data-action="close-modal" aria-label="Tutup">${I('close')}</button></div><div class="card-body"><p class="help">${esc(v.reason)} · ${date(v.created)} · SHA-256 ${esc(v.sha256)}</p><pre class="code">${esc(v.diff||v.config)}</pre></div>`;dialog.showModal()}
async function rollbackDeploymentVersion(id){const m=state.machines.find(m=>m.id===selectedMachine);showDialog('Rollback konfigurasi',`<div class="notice">${I('alert')}<span>Konfigurasi aktif <b>${esc(m.name)}</b> akan di-snapshot dulu, lalu versi <b>${esc(id)}</b> diterapkan ulang.</span></div>${field('Ketik nama mesin: '+m.name,'confirmation')}`,async d=>{await api('/machines/'+selectedMachine+'/deployments/'+id+'/rollback','POST',d);deployVersions=await api('/machines/'+selectedMachine+'/deployments');toast('Rollback dimulai. Snapshot current sudah dibuat.')});$('#modal button[type="submit"]').textContent='Rollback'}

async function previewJob(id){const j=await api('/jobs/'+id);const dialog=$('#modal');dialog.innerHTML=`<div class="dialog-head"><h2>Build ${j.id.slice(0,8)}</h2><button class="iconbtn" data-action="close-modal" aria-label="Tutup">${I('close')}</button></div><div class="card-body"><p class="help">${statusBadge(j.status)} · BIRD 2.19.2</p><pre class="code">${esc(j.config||j.log||'Konfigurasi belum tersedia.')}</pre></div>`;dialog.showModal()}
async function download(id){const j=await api('/jobs/'+id);if(!j.config)throw Error('Build belum menghasilkan konfigurasi.');const url=URL.createObjectURL(new Blob([j.config],{type:'text/plain'}));const a=document.createElement('a');a.href=url;a.download=`bird-${j.location}-${j.machine}-${j.id.slice(0,8)}.conf`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
function bindContent(){const qs=$('#peer-search');if(qs)qs.oninput=e=>{const pos=e.target.selectionStart;search=e.target.value;page=1;render();$('#peer-search').focus();$('#peer-search').setSelectionRange(pos,pos)};if($('#peer-family'))$('#peer-family').onchange=e=>{family=e.target.value;page=1;render()};if($('#peer-location'))$('#peer-location').onchange=async e=>{selectedLocation=e.target.value;detail=await api('/locations/'+selectedLocation);page=1;render()};if($('#editor-file'))$('#editor-file').onchange=async e=>{detail[editorFile]=$('#yaml-editor').value;editorFile=e.target.value;if(editorFile.endsWith('.j2') && typeof detail[editorFile] === 'undefined'){try{const r=await api('/locations/'+selectedLocation+'/templates/'+editorFile);detail[editorFile]=r.content;}catch(err){toast(err.message);}}render()};if($('#deploy-machine'))$('#deploy-machine').onchange=async e=>{selectedMachine=e.target.value;selectedJob=null;deployVersions=await api('/machines/'+selectedMachine+'/deployments');render()}}
async function action(a){if(a==='logout'){await api('/logout','POST',{});session=null;clearInterval(poll);login(false)}else if(a==='menu')$('.sidebar').classList.toggle('open');else if(a==='close-modal')$('#modal').close();else if(a==='refresh'){await refresh();if(view==='location'||view==='peers'){detail=await api('/locations/'+selectedLocation);try{detail.templates=await api('/locations/'+selectedLocation+'/templates')}catch(e){}}render();toast('Data dimuat ulang.')}else if(a==='add-location')addLocation();else if(a==='add-machine')addMachine();else if(a==='edit-policy')editPolicy();else if(a==='add-peer')addPeer();else if(a==='add-switch')addSwitch();else if(a==='add-node')addNode();else if(a==='add-iixji')addIixjiMember();else if(a==='edit-machine')editMachine();else if(a==='deploy'){if(selectedMachine)deployVersions=await api('/machines/'+selectedMachine+'/deployments');await navigate('deploy');}else if(a==='prev-page'){page=Math.max(1,page-1);render()}else if(a==='next-page'){page++;render()}else if(a==='save-config'){detail[editorFile]=$('#yaml-editor').value;if(editorFile.endsWith('.j2')){await api('/locations/'+selectedLocation+'/templates/'+editorFile,'PUT',{content:detail[editorFile]});toast('Template disimpan.');}else{await api('/locations/'+selectedLocation,'PUT',{general:detail.general,clients:detail.clients,revision:detail.revision});detail=await api('/locations/'+selectedLocation);try{detail.templates=await api('/locations/'+selectedLocation+'/templates')}catch(e){};await refresh();toast('Draft disimpan. Buat build baru untuk menerapkan perubahan.')}render();}else if(a==='check-ssh'){toast('Memeriksa koneksi SSH…');const r=await api('/machines/'+selectedMachine+'/check','POST',{});await refresh();render();toast(r.output.slice(0,150))}else if(a==='build'){const r=await api('/machines/'+selectedMachine+'/build','POST',{});selectedJob=r.id;await refresh();render();toast('Build masuk antrean.')}else if(a==='validate'){await api('/jobs/'+currentJob().id+'/validate','POST',{});await refresh();render()}else if(a==='deploy-confirm'){const m=state.machines.find(m=>m.id===selectedMachine),j=currentJob();showDialog('Tinjau deployment',`<div class="notice">${I('alert')}<span>Konfigurasi aktif <b>${esc(m.name)}</b> (${esc(m.host)}) akan diganti. Agent memvalidasi ulang, membuat backup, lalu menjalankan reload BIRD.</span></div><p class="help">Build ${j.id.slice(0,8)} · SHA-256 ${j.sha256.slice(0,16)}…<br>Perubahan dapat memicu restart sesi BGP yang terdampak.</p>${field('Ketik nama mesin: '+m.name,'confirmation')}`,async d=>{await api('/jobs/'+j.id+'/deploy','POST',d);toast('Deployment dimulai. Pantau hasil pada log build.')});$('#modal button[type="submit"]').textContent='Terapkan konfigurasi'}}
document.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b||b.disabled||(b.type==='submit'&&b.form))return;try{if(b.dataset.member)await reviewMember(b.dataset.member);else if(b.dataset.view)await navigate(b.dataset.view);else if(b.dataset.location)await openLocation(b.dataset.location,b.dataset.config==='true');else if(b.dataset.machine){selectedMachine=b.dataset.machine;selectedJob=null;await navigate('deploy')}else if(b.dataset.tab){locationTab=b.dataset.tab;render()}else if(b.dataset.removePeer)removePeer(b.dataset.removePeer);else if(b.dataset.assignPeer)await assignConnection(b.dataset.assignPeer);else if(b.dataset.jobPreview)await previewJob(b.dataset.jobPreview);else if(b.dataset.jobDownload)await download(b.dataset.jobDownload);else if(b.dataset.versionDetail)await showDeploymentVersion(b.dataset.versionDetail);else if(b.dataset.versionRollback)await rollbackDeploymentVersion(b.dataset.versionRollback);else if(b.dataset.addPort)await addPort(Number(b.dataset.addPort));else if(b.dataset.deleteNode)await deleteNode(Number(b.dataset.deleteNode));else if(b.dataset.managePorts)await managePorts(Number(b.dataset.managePorts));else if(b.dataset.editIixji)await editIixjiMember(b.dataset.editIixji);else if(b.dataset.delIixji)await delIixjiMember(b.dataset.delIixji);else if(b.dataset.discoverSwitch)await discoverSwitch(Number(b.dataset.discoverSwitch));else if(b.dataset.selectJob){selectedJob=b.dataset.selectJob;render()}else if(b.dataset.action){b.disabled=true;await action(b.dataset.action)}}catch(err){toast(err.message)}finally{if(b.isConnected)b.disabled=false}});

async function assignConnection(asn){
  const ls=await api('/switches');
  showDialog('Assign Port AS' + asn,
    `<div class="form-grid">
       <div>
         <label class="label" for="f-switch_id">Switch</label>
         <select class="field" id="f-switch_id" name="switch_id">
           ${ls.map(s => `<option value="${s.id}">${esc(s.name)} (${esc(s.ip)})</option>`).join('')}
         </select>
       </div>
       ${field('Port', 'port_number', 'mis. xe-0/0/2')}<div><span class=label>Tipe port fisik</span><div>Belum terdeteksi</div><small>Data kecepatan interface SNMP belum tersedia.</small></div>
       
       <div>
         <label class="label" for="f-status">Status</label>
         <select class="field" id="f-status" name="status">
           <option value="up">up</option>
           <option value="down">down</option>
         </select>
       </div>
       ${field('Kapasitas layanan / Bandwidth', 'bandwidth', 'mis. 1G', '1G')}
       ${field('MAC Address', 'mac_address', 'e.g. 00:11:22:33:44:55')}
     </div>`,
    async d => {
      await api('/peers/'+asn+'/assign', 'POST', d);
      toast('Port berhasil ditetapkan.');
      if(view==='peers'||view==='location') { detail=await api('/locations/'+selectedLocation); render(); }
    }
  );
}

function startPolling(){clearInterval(poll);poll=setInterval(async()=>{if(!session||(view!=='members'&&!state.jobs.some(j=>['generating','validating','deploying'].includes(j.status))))return;try{await refresh();if(view==='deploy'||view==='activity'||view==='members')render()}catch{}},2500)}
const context=document.modelContext;if(context?.registerTool){try{Promise.resolve(context.registerTool({name:'inspect_route_server_inventory',description:'Read locations and registered route servers visible to the signed-in administrator.',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true},execute:async input=>{if(!input||Object.keys(input).length)throw Error('No arguments accepted.');if(!session)throw Error('Sign in first.');await refresh();return {locations:state.locations,machines:state.machines}}})).catch(()=>{})}catch{}}
try{session=await api('/session');if(session.user){await refresh();shell();startPolling()}else login(session.setup)}catch(e){$('#app').innerHTML=empty('Dashboard belum dapat dimuat',esc(e.message),'alert')}
function iixjiPage(){
  if(!window.iixji_data) return empty('Memuat data', '');
  return heading('Daftar Member IIX-JI','Daftar member ISP Lokal Jawa Timur di IIX-JI dan ISP Luar yang sudah Melapor',btn('Tambah Member','add-iixji','plus','primary'))+
  `<div class="card"><div class="card-head"><h2>Member IIX-JI</h2></div>
  <div class="table-wrap"><table><thead><tr><th>ASN</th><th>Nama Jaringan</th><th>Tipe</th><th>Status</th><th>Kontak</th><th>Catatan</th><th></th></tr></thead><tbody>
  ${window.iixji_data.map(x=>`<tr><td>AS${esc(x.asn)}</td><td><strong>${esc(x.name)}</strong></td><td>${esc(x.type)}</td><td>${esc(x.status)}</td><td>${esc(x.contact)}</td><td>${esc(x.notes)}</td><td>
  <button class="btn small table-action" data-edit-iixji="${x.id}">Edit</button>
  <button class="btn small table-action" data-del-iixji="${x.id}">Hapus</button>
  </td></tr>`).join('')||'<tr><td colspan="7">Belum ada member.</td></tr>'}
  </tbody></table></div></div>`;
}

function addIixjiMember(){
  showDialog('Tambah Member IIX-JI',`<div class="form-grid">
  ${field('ASN','asn','Contoh: 12345','','type="number"')}
  ${field('Nama Jaringan','name','')}
  <div><label class="label">Tipe</label><select name="type" class="field"><option>Lokal Jatim</option><option>Luar Jatim</option></select></div>
  <div><label class="label">Status</label><select name="status" class="field"><option>Aktif</option><option>Melapor</option></select></div>
  ${field('Kontak','contact','')}
  ${field('Catatan','notes','','','')}</div>`, async d=>{
    await api('/iixji-members','POST',d); window.iixji_data=await api('/iixji-members'); render();;toast('Member ditambahkan.'); // Wait! `api` prepends /api!
    // So if path is `/iixji-members`, `api` will request `/api/iixji-members`!
    // I should check `api()` implementation.
  })
}

async function editIixjiMember(id){
  const x = window.iixji_data.find(m => m.id == id);
  if(!x) return;
  showDialog('Edit Member IIX-JI',`<div class="form-grid">
  ${field('ASN','asn','Contoh: 12345',x.asn,'type="number"')}
  ${field('Nama Jaringan','name','',x.name)}
  <div><label class="label">Tipe</label><select name="type" class="field"><option ${x.type==='Lokal Jatim'?'selected':''}>Lokal Jatim</option><option ${x.type==='Luar Jatim'?'selected':''}>Luar Jatim</option></select></div>
  <div><label class="label">Status</label><select name="status" class="field"><option ${x.status==='Aktif'?'selected':''}>Aktif</option><option ${x.status==='Melapor'?'selected':''}>Melapor</option></select></div>
  ${field('Kontak','contact','',x.contact)}
  ${field('Catatan','notes','',x.notes,'')}</div>`, async d=>{
    await api('/iixji-members/'+id,'PUT',d);
    toast('Member diperbarui.');
    if(view==='iixji'){ window.iixji_data=await api('/iixji-members'); render(); }
  })
}

async function delIixjiMember(id){
  const x = window.iixji_data.find(m => m.id == id);
  showDialog('Hapus Member IIX-JI',`<p>Hapus member <b>${esc(x.name)}</b>?</p>`,async ()=>{
    await api('/iixji-members/'+id,'DELETE');
    toast('Member dihapus.');
    if(view==='iixji'){ window.iixji_data=await api('/iixji-members'); render(); }
  });
  $('#modal button[type="submit"]').textContent='Hapus';
}

document.addEventListener('click',e=>{const v=e.target.dataset.portGraph;if(v){const [s,p]=v.split(':');showDialog('Grafik utilisasi',`<img class="port-graph" src="/api/switches/${s}/ports/${p}/graph" alt="Grafik utilisasi port">`,async()=>{});}});

async function syslogPage(){
  const summary = await api('/syslog/summary');
  const events = await api('/syslog/events');
  const logs = await api('/syslog/logs');
  
  let html = heading('Syslog & Analisis Switch', 'Monitoring event syslog, korelasi port, vendor MAC, dan masalah jaringan.');
  
  html += `<div class="metrics">
    <div class="metric"><div class="metric-val">${summary.logs||0}</div><div class="metric-lbl">Total Logs (36 Jam)</div></div>
    <div class="metric"><div class="metric-val">${summary.events||0}</div><div class="metric-lbl">Total Events Terdeteksi</div></div>
  </div>`;
  
  html += `<div class="card mb"><div class="card-head"><h2>Daftar Masalah Terdeteksi</h2></div><div class="table-wrap"><table>
  <thead><tr><th>Timestamp</th><th>Switch / Host</th><th>Port / MAC</th><th>Vendor</th><th>Tipe Problem</th><th>Dedupe Count</th><th>Korelasi Owner vs Identity</th></tr></thead><tbody>`;
  
  for(const e of (events.items||[])){
    let corrInfo = '-';
    if(e.correlation){
      try {
        const c = typeof e.correlation === 'string' ? JSON.parse(e.correlation) : e.correlation;
        const owner = c.admin_port ? `AS${c.admin_port.member_asn} (${c.admin_port.member_name||''})` : 'Unassigned';
        corrInfo = `Owner: ${esc(owner)} | Port: ${esc(c.admin_port?.port_number||'-')}`;
        if(c.mismatch) corrInfo += ` <span class="badge red">Mismatch</span>`;
      } catch(err){}
    }
    html += `<tr>
      <td>${date(e.last_ts)}</td>
      <td><strong>${esc(e.host||e.source_ip)}</strong><br><small>${esc(e.source_ip)}</small></td>
      <td>Interface: ${esc(e.interface||'-')}<br><small>MAC: ${esc(e.mac||'-')}</small></td>
      <td>${esc(e.vendor||'Unknown')}</td>
      <td><span class="badge amber">${esc(e.type)}</span><br><small>Sev: ${e.severity} | Conf: ${e.confidence}</small></td>
      <td><strong>${e.count}</strong></td>
      <td>${corrInfo}</td>
    </tr>`;
  }
  if(!(events.items||[]).length) html += `<tr><td colspan="7">Belum ada problem terdeteksi</td></tr>`;
  html += `</tbody></table></div></div>`;
  
  html += `<div class="card"><div class="card-head"><h2>Raw Syslog Feed</h2></div><div class="table-wrap"><table>
  <thead><tr><th>Timestamp</th><th>Source IP / Host</th><th>Pri / Sev</th><th>Interface / MAC</th><th>Vendor</th><th>Message</th></tr></thead><tbody>`;
  
  for(const l of (logs.items||[]).slice(0, 50)){
    html += `<tr>
      <td>${date(l.ts)}</td>
      <td>${esc(l.host||l.source_ip)}<br><small>${esc(l.source_ip)}</small></td>
      <td>${l.pri} / Sev ${l.severity}</td>
      <td>${esc(l.interface||'-')}<br><small>${esc(l.mac||'-')}</small></td>
      <td>${esc(l.vendor||'Unknown')}</td>
      <td class="mono small">${esc(l.message)}</td>
    </tr>`;
  }
  if(!(logs.items||[]).length) html += `<tr><td colspan="6">Belum ada syslog diterima</td></tr>`;
  html += `</tbody></table></div></div>`;
  
  return html;
}


async function statsPage(){
  const cfg = await api('/stats/config');
  let html = heading('Stats & Grafik', 'Pilih grafik port switch untuk dipublikasikan ke container publik (Port 8991).');
  
  html += `<div class="card"><div class="row"><h3>Daftar Port Publik</h3><a href="${cfg.public_url}" target="_blank" class="btn small">Buka Halaman Publik</a></div>
  <table class="table"><thead><tr><th>Pilih</th><th>Switch</th><th>Port</th><th>Bandwidth</th><th>Member AS</th><th>Tersedia</th></tr></thead><tbody>`;
  
  cfg.ports.forEach(p => {
    html += `<tr>
      <td><input type="checkbox" class="stat-port-cb" data-id="${p.port_id}" ${p.public_enabled ? 'checked' : ''}></td>
      <td>${esc(p.node_name)} - ${esc(p.switch_name)}</td>
      <td>${esc(p.port_number)}</td>
      <td>${esc(p.bandwidth)}</td>
      <td>AS${p.member_asn}</td>
      <td>${p.rrd_available ? '<span class="badge success">Ya</span>' : '<span class="badge warning">Tdk</span>'}</td>
    </tr>`;
  });
  
  html += `</tbody></table></div>`;
  
  html += `<div class="card"><h3>Grup Agregat (Tampil di Publik)</h3>
  <div id="stats-groups">`;
  
  if(!cfg.groups || cfg.groups.length===0){
    cfg.groups = [{id:0, name:'Agregat Total', mode:'all', port_ids:[], enabled:1}];
  }
  
  cfg.groups.forEach((g, idx) => {
    html += `<div class="form-grid stats-group" data-idx="${idx}">
      <input type="text" class="field g-name" value="${esc(g.name)}" placeholder="Nama Grup">
      <select class="field g-mode">
        <option value="selected" ${g.mode==='selected'?'selected':''}>Port Terpilih</option>
        <option value="all" ${g.mode==='all'?'selected':''}>Semua port yang dipublikasikan</option>
      </select>
      <label><input type="checkbox" class="g-enabled" ${g.enabled?'checked':''}> Tampilkan</label>
      <div>${cfg.ports.map(p=>`<label><input class="g-port" type="checkbox" value="${p.port_id}" ${(g.port_ids||[]).includes(p.port_id)?'checked':''}>${esc(p.switch_name)} / ${esc(p.port_number)} (AS${p.member_asn})</label>`).join('')}</div>
    </div>`;
  });
  
  html += `</div></div>
  <div class="row"><button class="btn primary" id="btn-save-stats">Simpan Pengaturan</button></div>`;
  
  setTimeout(() => {
    const btn = document.getElementById('btn-save-stats');
    if(btn) btn.addEventListener('click', async () => {
      const ports = Array.from(document.querySelectorAll('.stat-port-cb')).map(cb => ({
        port_id: parseInt(cb.dataset.id),
        enabled: cb.checked ? 1 : 0
      }));
      const groups = Array.from(document.querySelectorAll('.stats-group')).map(el => ({
        name: el.querySelector('.g-name').value,
        mode: el.querySelector('.g-mode').value,
        enabled: el.querySelector('.g-enabled').checked ? 1 : 0,
        port_ids: Array.from(el.querySelectorAll('.g-port:checked')).map(cb=>Number(cb.value))
      }));
      await api('/stats/config', 'POST', {ports, groups});
      toast('Pengaturan grafik disimpan');
      render();
    });
  }, 100);
  
  return html;
}
