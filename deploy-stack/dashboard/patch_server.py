import re

with open('server.py', 'r') as f:
    content = f.read()

new_routes = '''            if method=='POST' and path=='/api/ports':return self.response(create_port(d),201)
            match=re.fullmatch(r'/api/peers/(\d+)/assign',path)
            if method=='POST' and match:return self.response(assign_peer_port(int(match[1]),d))'''

content = content.replace("            if method=='POST' and path=='/api/ports':return self.response(create_port(d),201)", new_routes)

with open('server.py', 'w') as f:
    f.write(content)
