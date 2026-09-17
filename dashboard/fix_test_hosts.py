import re
with open('tests/test_app.py', 'r') as f:
    src = f.read()

old_args = "        args = app.ssh_args({'id': mid, 'ssh_user': 'root'})"
new_args = """        open(app.DATA / 'hosts', 'w').close()
        with patch.dict(os.environ, {'MIMBAR_KNOWN_HOSTS': str(app.DATA / 'hosts')}):
            args = app.ssh_args({'id': mid, 'ssh_user': 'root', 'ssh_key': 'abc', 'ssh_port': 22, 'host': '1.2.3.4'})"""

src = src.replace(old_args, new_args)

with open('tests/test_app.py', 'w') as f:
    f.write(src)
