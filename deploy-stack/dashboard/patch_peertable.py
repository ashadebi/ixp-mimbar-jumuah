with open('dist/app.js', 'r') as f:
    content = f.read()

old_td = "<td>${p.source==='YAML'?`<button class=\"iconbtn table-action\" data-remove-peer=\"${esc(p.ip)}\" aria-label=\"Hapus peer ${esc(p.ip)}\">${I('close')}</button>`:''}</td>"
new_td = "<td>${p.source==='YAML'?`<button class=\"iconbtn table-action\" data-remove-peer=\"${esc(p.ip)}\" aria-label=\"Hapus peer ${esc(p.ip)}\">${I('close')}</button>`:''}<button class=\"iconbtn table-action\" data-assign-peer=\"${p.asn}\" title=\"Assign to switch\">${I('server')}</button></td>"

if old_td in content:
    content = content.replace(old_td, new_td)
    with open('dist/app.js', 'w') as f:
        f.write(content)
    print("Success")
else:
    print("Not found")
