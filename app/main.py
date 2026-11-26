"""Local desktop launcher. The API only listens on loopback with a session token."""
import argparse,json,mimetypes,os,re,secrets,sys,threading,traceback,webbrowser
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs,unquote
from core import HERE,LABELS,import_catalogue,save_json
from full_engine import FullEngine as Engine
import owned_items
import number_preview

TITLE='Naraka Atelier'

def status_payload(engine):
    """A live journal belongs to the worker; only idle journals need recovery."""
    def active():
        return {'build':{'ok':False,'state':'applying','version':engine.manifest['catalogue_version'],'errors':[],
                         'fingerprint_files':len(engine.disk['expected'])+len(engine.manifest['critical'])},
                'job':dict(engine.job),'profile':engine.disk,'features':engine.resolve_features(),'pending':bool(engine.pending)}
    if engine.job['busy']:return active()
    build=engine.check_build()
    if engine.job['busy']:return active()
    return {'build':build,'job':dict(engine.job),'profile':engine.disk,'features':engine.resolve_features(),'pending':bool(engine.pending)}
LOADING_HTML=('<!doctype html><html><body style="margin:0;height:100vh;display:grid;place-items:center;background:#0f141b;'
    'color:#d8e1ec;font:15px Segoe UI,sans-serif"><div style="text-align:center"><div style="font-size:22px;letter-spacing:.2em">'
    'NARAKA <b>ATELIER</b></div><p style="color:#93a3b8">Loading catalogue and checking the client…</p></div></body></html>')

def focus_existing_window():
    """Bring the running instance's window to the front. Returns False if there is none."""
    import ctypes
    user32=ctypes.windll.user32
    hwnd=user32.FindWindowW(None,TITLE)
    if not hwnd:return False
    if user32.IsIconic(hwnd):user32.ShowWindow(hwnd,9)  # SW_RESTORE
    else:user32.ShowWindow(hwnd,5)  # SW_SHOW
    # Windows only lets the foreground process hand over focus; ALT tap unlocks it.
    user32.keybd_event(0x12,0,0,0);user32.keybd_event(0x12,0,2,0)
    user32.SetForegroundWindow(hwnd)
    return True

def acquire_instance_lock(state):
    """One server per state directory. Never read the lock byte: on Windows, reading a
    region another process has locked raises PermissionError (Errno 13). Locking past EOF
    is allowed, so the file can stay empty."""
    import msvcrt
    state.mkdir(parents=True,exist_ok=True)
    instance=(state/'server.lock').open('a+b');instance.seek(0)
    try:msvcrt.locking(instance.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:instance.close();return None
    return instance

def release_instance_lock(instance):
    import msvcrt
    try:instance.seek(0);msvcrt.locking(instance.fileno(),msvcrt.LK_UNLCK,1)
    except OSError:pass
    instance.close()

def main():
    p=argparse.ArgumentParser();p.add_argument('--no-browser',action='store_true',help='headless server only (testing)');p.add_argument('--browser',action='store_true',help='use the system browser instead of the app window');p.add_argument('--port',type=int,default=0);p.add_argument('--state-dir');p.add_argument('--compile-only',type=Path);a=p.parse_args()
    if not a.compile_only:
        state=Path(a.state_dir or Path(os.environ.get('LOCALAPPDATA',Path.home()))/'Naraka Atelier')
        instance=acquire_instance_lock(state)
        if instance is None:
            # Already running: show its window instead of starting a second server.
            if not a.no_browser and not focus_existing_window():
                session={}
                try:session=json.loads((state/'session.json').read_text(encoding='utf8'))
                except (OSError,ValueError):pass
                if session.get('url'):webbrowser.open(session['url'])
            return
        try:return run_app(a)
        finally:release_instance_lock(instance)
    run_app(a)

def run_app(a):
    engine=None;token=secrets.token_urlsafe(32);job_gate=threading.Lock();ui={'close':None}
    def make_engine():
        nonlocal engine
        engine=Engine(a.state_dir);return engine
    if a.compile_only:
        make_engine()
        # Packaging QA / read-only planning: writes candidates to app state only.
        status=engine.check_build(strict=True)
        if not status['ok']:raise ValueError('; '.join(status['errors']))
        selections=json.loads(a.compile_only.read_text(encoding='utf8'))
        candidate,hashes=engine.build(selections)
        save_json(engine.state/'compile-result.json',{'passed':True,'candidate':str(candidate),'hashes':hashes,'game_files_modified':False})
        return
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send(self,body,status=200,mime='application/json'):
            if isinstance(body,(dict,list)):body=json.dumps(body,ensure_ascii=False).encode('utf8')
            if isinstance(body,str):body=body.encode('utf8')
            self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)))
            self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; connect-src 'self'")
            self.end_headers();self.wfile.write(body)
        def allowed(self,api=False):
            expected='127.0.0.1:'+str(self.server.server_port)
            if self.headers.get('Host')!=expected:return False
            origin=self.headers.get('Origin')
            if origin and origin!='http://'+expected:return False
            if api and self.headers.get('X-Session-Token')!=token:return False
            return True
        def do_GET(self):
            if not self.allowed():return self.send({'error':'Invalid local host'},403)
            u=urlparse(self.path)
            if u.path.startswith('/api/') and not self.allowed(True):return self.send({'error':'Session token required'},403)
            try:
                if u.path=='/api/bootstrap':return self.send({'catalogue':engine.catalogue,'items':[i for i in engine.items.values() if not i.get('synthetic')],'receivers':[i for i in engine.items.values() if i.get('synthetic')],'hairEffects':[{'id':i,'label':engine.row('HairEffect','HairEffect_Effect',i)['_Name']} for i in engine.rows['HairEffect']['HairEffect_Effect']],'labels':LABELS,'coverage':engine.coverage,'active':engine.baseline_active(),'profile':engine.disk,'features':engine.resolve_features(),'ownership':owned_items.load(engine),'ordering':engine.display_order(),'version':engine.manifest['catalogue_version'],'state_dir':str(engine.state),'game':str(engine.game)})
                if u.path=='/api/status':return self.send(status_payload(engine))
                if u.path=='/api/targets':
                    q=parse_qs(u.query);src=engine.items[q['source'][0]];hero=q.get('hero',[None])[0]
                    category=q.get('category',[None])[0];kind=q.get('kind',[None])[0]
                    def target_ok(i):
                        if category and i['c']!=category or kind and i.get('kind')!=kind or i.get('synthetic'):return False
                        if engine.compatible(src,i,hero):return False
                        if i['c']=='effect' and i['kind']=='weapon':
                            row=engine.row('WeaponSkin','WeaponSkin_SkinBattleEffect',int(str(i['id'])[1:]));suitable=row['_SuitableWeaponSkin']
                            visual=q.get('visual',[None])[0];visual=int(visual) if visual else engine.effective_weapon(src['key'],engine.disk['selections'])
                            if not engine.effect_fits_weapon(visual,int(str(i['id'])[1:])):return False
                        return True
                    return self.send({'keys':[i['key'] for i in engine.items.values() if target_ok(i)]})
                if u.path=='/api/controls':
                    q=parse_qs(u.query);key=q['target'][0]
                    if not engine.items[key]['support']['available']:raise ValueError('Target is unsupported by the installed native build')
                    return self.send({'controls':engine.controls(key,int(q.get('variant',[0])[0]))})
                if u.path=='/':
                    html=(HERE/'web/index.html').read_text(encoding='utf8').replace('__SESSION_TOKEN__',token)
                    return self.send(html,mime='text/html; charset=utf-8')
                if u.path.startswith('/icons/'):
                    name=unquote(u.path[7:])
                    if Path(name).name!=name or '/' in name or '\\' in name:return self.send({'error':'Invalid icon'},400)
                    path=engine.catalogue_dir/'icons'/name
                elif u.path in ('/app.js','/workflow.js','/style.css','/three.min.js','/OrbitControls.js','/colour-sketch.js'):path=HERE/'web'/u.path[1:]
                else:return self.send({'error':'Not found'},404)
                if not path.is_file():return self.send({'error':'Not found'},404)
                return self.send(path.read_bytes(),mime=mimetypes.guess_type(str(path))[0] or 'application/octet-stream')
            except Exception as exc:self.send({'error':str(exc)},400)
        def do_POST(self):
            if not self.allowed(True):return self.send({'error':'Invalid local session'},403)
            try:
                size=int(self.headers.get('Content-Length','0'))
                limit=160_000_000 if self.path=='/api/import' else 300_000
                if size>limit:
                    # Drain modest oversize bodies so ordinary HTTP clients
                    # receive the JSON413 instead of a reset while uploading.
                    self.connection.settimeout(5)
                    if size<=4_000_000:
                        remaining=size
                        while remaining:
                            chunk=self.rfile.read(min(65536,remaining))
                            if not chunk:break
                            remaining-=len(chunk)
                    self.close_connection=True
                    return self.send({'error':'Request exceeds the allowed size'},413)
                if size<=0:raise ValueError('Request body is empty')
                self.connection.settimeout(15)
                raw=self.rfile.read(size)
                if len(raw)!=size:raise ValueError('Incomplete request body')
                if self.path=='/api/import':
                    if not job_gate.acquire(blocking=False):raise ValueError('Wait for the current operation')
                    path=None;accepted=False
                    try:
                        path=engine.state/('catalogue-'+secrets.token_hex(8)+'.zip');path.write_bytes(raw)
                        folder,data,digest=import_catalogue(path,engine.state/'catalogues',engine.manifest['catalogue_version'])
                        attrs=('catalogue','catalogue_dir','catalogue_digest','items','coverage','skill_groups','effect_families','effect_types')
                        old={k:getattr(engine,k) for k in attrs}
                        try:
                            engine.catalogue=data;engine.catalogue_dir=folder;engine.catalogue_digest=digest;engine.load_items();engine.coverage=engine.audit()
                            unsupported=[i['key'] for i in engine.items.values() if not i['support']['available']]
                            if unsupported:raise ValueError('Catalogue contains entries unsupported by this installed build: '+', '.join(unsupported[:8]))
                            engine.validate(engine.disk['selections'])
                        except Exception:
                            for k,v in old.items():setattr(engine,k,v)
                            save_json(engine.state/'catalogue-coverage.json',engine.coverage);raise
                        save_json(engine.state/'settings.json',{'catalogue':str(path)})
                        accepted=True
                    finally:
                        if path is not None and not accepted:path.unlink(missing_ok=True)
                        job_gate.release()
                    return self.send({'imported':True,'built':data['built']})
                payload=json.loads(raw)
                if self.path=='/api/number-preview':
                    if not isinstance(payload,dict) or set(payload)-{'target','numbers'}:raise ValueError('Unexpected preview fields')
                    return self.send(number_preview.preview(engine,payload.get('target'),payload.get('numbers')))
                if self.path=='/api/ownership':return self.send(owned_items.save(engine,payload))
                if self.path=='/api/validate':
                    jobs=engine.validate(payload['selections']);features=engine.resolve_features(payload.get('features'));return self.send({'valid':True,'native_jobs':len(jobs),'features':features})
                if self.path in ('/api/apply','/api/recover'):
                    if not job_gate.acquire(blocking=False):raise ValueError('An operation is already running')
                    try:
                        selections=payload.get('selections',[])
                        features=None
                        if self.path=='/api/apply':
                            engine.validate(selections);features=engine.resolve_features(payload.get('features'))
                    except Exception:job_gate.release();raise
                    operation=self.path
                    engine.job={'id':secrets.token_hex(16),'busy':True,'message':'Checking client and game closure','error':None,'percent':2,'phase':'validation'}
                    started_job=dict(engine.job)
                    def run():
                        try:
                            def progress(message):
                                if isinstance(message,dict):engine.job.update(message);return
                                engine.job.update(message=message)
                                match=re.search(r'(Compiling|Packing and verifying) (\d+)/(\d+)',message)
                                if match:
                                    base,span=(15,35) if match[1]=='Compiling' else (50,26)
                                    engine.job.update(percent=base+span*int(match[2])/int(match[3]),phase=match[1])
                                elif message.startswith('Saving verified'):engine.job.update(percent=78,phase='backup')
                            result=engine.recover() if operation.endswith('recover') else engine.apply(selections,progress,features=features)
                            engine.job.update(busy=False,message='Completed — ready for your in-game check',result=result,percent=100,phase='complete')
                        except Exception as exc:
                            engine.job.update(busy=False,message='Operation stopped',error=str(exc))
                            save_json(engine.state/'last-error.json',{'error':str(exc),'trace':traceback.format_exc()})
                        finally:job_gate.release()
                    threading.Thread(target=run,daemon=True).start();return self.send({'started':True,'job':started_job})
                if self.path=='/api/shutdown':
                    if engine.job['busy']:raise ValueError('Cannot exit during a resource operation')
                    self.send({'closed':True});threading.Thread(target=ui['close'] or self.server.shutdown,daemon=True).start();return
                self.send({'error':'Not found'},404)
            except Exception as exc:self.send({'error':str(exc)},400)
    def start_server():
        make_engine()
        server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler);url='http://127.0.0.1:'+str(server.server_port)
        save_json(engine.state/'session.json',{'url':url,'port':server.server_port})
        if sys.stdout:print(url,flush=True)
        return server,url
    def serve_blocking():
        server,url=start_server()
        if a.browser:webbrowser.open(url)
        try:server.serve_forever()
        finally:server.server_close()
    if a.no_browser or a.browser:return serve_blocking()
    try:
        import webview
    except Exception:
        # No embedded-window support: fall back to the system browser.
        a.browser=True;return serve_blocking()
    # App window: the server lives inside this process, so closing the window
    # stops the server and exits — no hidden background process is left behind.
    window=webview.create_window(TITLE,html=LOADING_HTML,width=1440,height=920,min_size=(960,640),background_color='#0f141b',text_select=True)
    state={'server':None}
    ui['close']=window.destroy
    def boot():
        try:
            server,url=start_server();state['server']=server
            threading.Thread(target=server.serve_forever,daemon=True).start()
            window.load_url(url)
        except Exception as exc:
            window.load_html('<body style="background:#0f141b;color:#f0b4b4;font:15px Segoe UI;padding:32px"><h2>Naraka Atelier could not start</h2><pre style="white-space:pre-wrap">'
                +str(exc).replace('&','&amp;').replace('<','&lt;')+'</pre></body>')
            save_json(Path(a.state_dir or Path(os.environ.get('LOCALAPPDATA',Path.home()))/'Naraka Atelier')/'last-error.json',{'error':str(exc),'trace':traceback.format_exc()})
    try:
        webview.start(boot,gui='edgechromium',private_mode=True)
    finally:
        server=state['server']
        if server:
            if engine is not None and engine.job.get('busy'):
                # Never cut off a resource write: keep serving until it finishes.
                while engine.job.get('busy'):threading.Event().wait(0.5)
            server.shutdown();server.server_close()

if __name__=='__main__':
    try:main()
    except Exception as exc:
        if '--compile-only' in sys.argv and '--state-dir' in sys.argv:
            save_json(Path(sys.argv[sys.argv.index('--state-dir')+1])/'compile-error.json',{'error':str(exc),'trace':traceback.format_exc()})
            sys.exit(1)
        if sys.stderr:traceback.print_exc()
        else:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0,str(exc),'Naraka Atelier — startup error',0x10)
        sys.exit(1)
