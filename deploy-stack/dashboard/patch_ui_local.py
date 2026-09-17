import re

with open('dist/app.js', 'r') as f:
    src = f.read()

old_add = "${field('Port SSH','ssh_port','','22','type=\"number\" min=\"1\" max=\"65535\"')}</div>"
new_add = "${field('Port SSH','ssh_port','','22','type=\"number\" min=\"1\" max=\"65535\"')}<div><label class=\"label\" for=\"f-ssh_key\">Kunci Privat SSH / Deploy Key</label><textarea id=\"f-ssh_key\" class=\"field\" name=\"ssh_key\" placeholder=\"Opsional, jika kosong gunakan default\"></textarea></div></div>"
if old_add in src:
    src = src.replace(old_add, new_add)
else:
    print("Warning: old_add not found")

add_func_old = "await api('/machines','POST',d);"
add_func_new = "if(!d.ssh_key) delete d.ssh_key; await api('/machines','POST',d);"
src = src.replace(add_func_old, add_func_new)

old_edit = "${field('Port SSH','ssh_port','',m.ssh_port,'type=\"number\" min=\"1\" max=\"65535\"')}</div>"
new_edit = "${field('Port SSH','ssh_port','',m.ssh_port,'type=\"number\" min=\"1\" max=\"65535\"')}<div><label class=\"label\" for=\"f-ssh_key\">Kunci Privat SSH</label><textarea id=\"f-ssh_key\" class=\"field\" name=\"ssh_key\" placeholder=\"Kunci Privat SSH (Kosongkan jika tidak diubah)\"></textarea><p class=\"help\">Kunci Privat SSH (Kosongkan jika tidak diubah)</p></div></div>"
if old_edit in src:
    src = src.replace(old_edit, new_edit)
else:
    print("Warning: old_edit not found")

edit_func_old = "await api('/machines/'+m.id,'PUT',{...d,revision:m.revision});"
edit_func_new = "if(!d.ssh_key) delete d.ssh_key; await api('/machines/'+m.id,'PUT',{...d,revision:m.revision});"
src = src.replace(edit_func_old, edit_func_new)

with open('dist/app.js', 'w') as f:
    f.write(src)
