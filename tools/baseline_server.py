"""Serve the unchanged baseline Game with the campaigns available in the input."""
import argparse
from pathlib import Path
from input_http_server import InputHTTPServer

def serve(host='127.0.0.1',port=8770,data_dir=None,enable_debug=False,trusted=None):
    import web_playtest as web
    from web_storage import Storage
    if not web.LEVELS:raise ValueError('Input has no baseline levels')
    web.SESSIONS.factory=lambda:web.Game((web.DEMOS or web.FORMAL)[0]['id'])
    web.DEBUG_SESSIONS.factory=lambda:web.Game((web.FORMAL or web.DEMOS)[0]['id'])
    class Handler(web.Handler):
        def do_GET(self):
            if self.path=='/menu.js':
                text=(web.ROOT/'web/menu.js').read_text(encoding='utf-8')
                text=text.replace('85 关',str(len(web.LEVELS))+' 关')
                return self.send(200,text.encode('utf-8'),'text/javascript; charset=utf-8')
            return super().do_GET()
    server=InputHTTPServer((host,port),Handler,trusted=trusted)
    server.secure_cookies=False;server.enable_debug=enable_debug
    server.storage=Storage(Path(data_dir or web.ROOT/'data')/'openrd.sqlite3')
    print(f'OpenRD baseline: http://{host}:{server.server_port}',flush=True)
    server.serve_forever()

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--host',default='127.0.0.1')
    ap.add_argument('--port',type=int,default=8770);ap.add_argument('--data-dir',type=Path)
    ap.add_argument('--enable-debug',action='store_true')
    ap.add_argument('--trusted-hosts','--trustedhosts')
    args=ap.parse_args();serve(args.host,args.port,args.data_dir,args.enable_debug,args.trusted_hosts)
