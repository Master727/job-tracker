import os,signal,subprocess,sys,time,urllib.request,json
from pathlib import Path
root=Path(__file__).resolve().parent; pidfile=root/'data/server.pid'
def healthy():
    try:
        with urllib.request.urlopen('http://localhost:3005/health',timeout=1) as r: return json.load(r).get('app')=='simple-job-tracker'
    except Exception: return False
if sys.argv[1]=='stop':
    if pidfile.exists():
        try: os.killpg(int(pidfile.read_text()),signal.SIGTERM)
        except ProcessLookupError: pass
        pidfile.unlink()
    print('Job Tracker stopped.'); sys.exit(0)
if not healthy():
    with (root/'data/server.log').open('a') as log:
        p=subprocess.Popen([sys.executable,str(root/'server.py')],cwd=root,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    pidfile.write_text(str(p.pid))
    for _ in range(40):
        if healthy(): break
        if p.poll() is not None: sys.exit('Could not start; see data/server.log. Another app may be using port 3005.')
        time.sleep(.25)
    else: sys.exit('Startup timed out; see data/server.log.')
print('Job Tracker is running at http://localhost:3005')
