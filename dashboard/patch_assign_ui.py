import re

with open('dist/app.js', 'r') as f:
    content = f.read()

new_func = '''
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
       ${field('Port', 'port_number', 'e.g. xe-0/0/2')}
       <div>
         <label class="label" for="f-type">Type</label>
         <select class="field" id="f-type" name="type">
           <option value="1G">1G</option>
           <option value="10G">10G</option>
           <option value="40G">40G</option>
           <option value="100G">100G</option>
         </select>
       </div>
       <div>
         <label class="label" for="f-status">Status</label>
         <select class="field" id="f-status" name="status">
           <option value="up">up</option>
           <option value="down">down</option>
         </select>
       </div>
       ${field('Bandwidth', 'bandwidth', 'e.g. 1G', '1G')}
     </div>`,
    async d => {
      await api('/peers/'+asn+'/assign', 'POST', d);
      toast('Port assigned.');
      if(view==='peers'||view==='location') { detail=await api('/locations/'+selectedLocation); render(); }
    }
  );
}
'''

if 'async function assignConnection' not in content:
    content = content.replace('function startPolling', new_func + '\nfunction startPolling')

old_event = 'else if(b.dataset.removePeer)removePeer(b.dataset.removePeer);'
new_event = 'else if(b.dataset.removePeer)removePeer(b.dataset.removePeer);else if(b.dataset.assignPeer)await assignConnection(b.dataset.assignPeer);'
if old_event in content and 'dataset.assignPeer' not in content:
    content = content.replace(old_event, new_event)

with open('dist/app.js', 'w') as f:
    f.write(content)
print("UI patched")
