"""Avoid Windows port sharing between independent resource/game sessions."""
import os
import socket
from urllib.parse import urlsplit
from http.server import ThreadingHTTPServer

def trusted_hosts(host, configured=None):
    values={'127.0.0.1','localhost','::1'}
    if configured is None:
        if host not in ('0.0.0.0','::'):values.add(host)
        try:
            values.add(socket.gethostname())
            values.update(row[4][0] for row in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET))
        except OSError:pass
    else:
        values.update(part.strip() for part in configured.split(',') if part.strip())
    result=set()
    for value in values:
        if any(c in value for c in '/@?#* ') or not value:raise ValueError('Trusted hosts must be exact hostnames or IP addresses, without scheme, port or wildcard')
        # IPv6 literals contain colons; other colon-bearing values are host:port mistakes.
        if ':' in value:
            try:socket.inet_pton(socket.AF_INET6,value)
            except OSError:raise ValueError('Trusted hosts must not include ports')
        result.add(value.lower().rstrip('.'))
    return result


def authority(value):
    if not value or any(c in value for c in '/@?#\\'):
        raise ValueError('Invalid Host header')
    parsed=urlsplit('//'+value)
    if not parsed.hostname or parsed.username or parsed.password:raise ValueError('Invalid Host header')
    return parsed.hostname.lower().rstrip('.'),parsed.port


class InputHTTPServer(ThreadingHTTPServer):
    allow_reuse_address=os.name!='nt'

    def __init__(self,address,handler,bind_and_activate=True,trusted=None):
        allowed=trusted_hosts(address[0],trusted)
        class CheckedHandler(handler):
            def parse_request(self):
                if not super().parse_request():return False
                try:
                    headers=self.headers.get_all('Host',[])
                    if len(headers)!=1:raise ValueError('Exactly one Host header is required')
                    name,port=authority(headers[0])
                    if name not in allowed:raise ValueError('Host is not trusted')
                    origin=self.headers.get('Origin')
                    if origin:
                        parsed=urlsplit(origin)
                        if parsed.scheme not in ('http','https') or parsed.path not in ('','/') or parsed.query or parsed.fragment:
                            raise ValueError('Invalid Origin')
                        origin_name,origin_port=authority(parsed.netloc)
                        default=443 if parsed.scheme=='https' else 80
                        if origin_name!=name or (origin_port or default)!=(port or default):raise ValueError('Cross-origin request rejected')
                except ValueError as exc:
                    self.send_error(403,str(exc));return False
                return True
        self.trusted_hosts=allowed
        super().__init__(address,CheckedHandler,bind_and_activate)

    def server_bind(self):
        if os.name=='nt' and hasattr(socket,'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        return super().server_bind()
