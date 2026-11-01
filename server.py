#!/usr/bin/env python3
"""Local, single-user application tracker. Python standard library only; no AI."""
import csv, io, json, os, re, sqlite3, urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from posting import import_posting, import_captured, PostingError

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'data/tracker.db'
# Resumes to choose from when logging an application; one per job title, as the Headless Headhunter teaches.
RESUME_DIR = Path(os.environ.get('JOB_TRACKER_RESUMES', Path.home() / 'Pavlo/Jobs'))
BASE = 'http://localhost:3005'
STAGES = ['Applied', 'Screen', 'Interview', 'Offer', 'Rejected', 'Withdrawn']
# Furthest stage reached; a rejection after an interview still counts as an interview for the resume grade.
PROGRESS = ['Applied', 'Screen', 'Interview', 'Offer']
SOURCES = ['LinkedIn', 'Indeed', 'Company site', 'Craigslist', 'Referral', 'Other']
# The Headless Headhunter's resume grades: one interview per N applications.
GRADES = [(10, 'A+'), (25, 'B'), (50, 'C-'), (75, 'D')]

def now(): return datetime.now(timezone.utc).isoformat()
def connect():
    c = sqlite3.connect(DB, timeout=30); c.row_factory = sqlite3.Row; return c
def init():
    (ROOT / 'data').mkdir(exist_ok=True)
    with connect() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS applications(id INTEGER PRIMARY KEY,company TEXT NOT NULL,role TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'Applied',applied TEXT NOT NULL,url TEXT DEFAULT '',notes TEXT DEFAULT '',thread_id TEXT DEFAULT '',updated TEXT NOT NULL)''')
        have = {r['name'] for r in c.execute('PRAGMA table_info(applications)')}
        for name in ('applied_at', 'posted_at', 'source', 'resume', 'furthest'):
            if name not in have: c.execute('ALTER TABLE applications ADD COLUMN '+name+" TEXT DEFAULT ''")
        c.execute("UPDATE applications SET status='Screen' WHERE status='Responded'")
        c.execute("UPDATE applications SET furthest=status WHERE furthest='' AND status IN ('Applied','Screen','Interview','Offer')")
        c.execute("UPDATE applications SET furthest='Applied' WHERE furthest=''")
    os.chmod(DB, 0o600)

def stamp(value):
    """Normalize an optional ISO timestamp from the browser; '' means unknown."""
    value = str(value or '').strip()
    if not value: return ''
    t = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if t.tzinfo is None: raise ValueError('Timestamps need a time zone.')
    return t.astimezone(timezone.utc).isoformat()
def further(current, status):
    current = current or 'Applied'
    if status not in PROGRESS: return current
    return status if PROGRESS.index(status) > PROGRESS.index(current) else current
def save_application(d):
    company = str(d.get('company', '')).strip(); role = str(d.get('role', '')).strip(); status = d.get('status', 'Applied')
    applied_at = stamp(d.get('applied_at')); posted_at = stamp(d.get('posted_at'))
    applied = str(d.get('applied') or (applied_at or now())[:10]); url = str(d.get('url', '')).strip()
    source = str(d.get('source', '')).strip(); resume = str(d.get('resume', '')).strip()[:200]
    if not company or not role or status not in STAGES: raise ValueError('Company, role and a valid status are required.')
    datetime.strptime(applied, '%Y-%m-%d')
    if url and not re.match(r'^https?://', url): raise ValueError('Use an http or https link.')
    if source and source not in SOURCES: raise ValueError('Unknown job board.')
    with connect() as db:
        old = db.execute('SELECT furthest FROM applications WHERE id=?', (int(d['id']),)).fetchone() if d.get('id') else None
        values = (company[:200], role[:300], status, applied, applied_at, posted_at, url, source, resume, str(d.get('notes', '')), further(old['furthest'] if old else '', status), now())
        if old:
            db.execute('UPDATE applications SET company=?,role=?,status=?,applied=?,applied_at=?,posted_at=?,url=?,source=?,resume=?,notes=?,furthest=?,updated=? WHERE id=?', values+(int(d['id']),)); return int(d['id'])
        if d.get('id'): raise ValueError('That application no longer exists.')
        return db.execute('INSERT INTO applications(company,role,status,applied,applied_at,posted_at,url,source,resume,notes,furthest,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', values).lastrowid
def set_status(app_id, status):
    if status not in STAGES: raise ValueError('Invalid status')
    with connect() as db:
        row = db.execute('SELECT furthest FROM applications WHERE id=?', (int(app_id),)).fetchone()
        if not row: raise ValueError('That application no longer exists.')
        db.execute('UPDATE applications SET status=?,furthest=?,updated=? WHERE id=?', (status, further(row['furthest'], status), now(), int(app_id)))
def grade(applications, interviews):
    """Letter grade for a resume, or '' until there is enough data to judge."""
    if not interviews and applications < 10: return ''
    ratio = applications / max(interviews, 1)
    return next((g for limit, g in GRADES if ratio <= limit), 'F')
def resume_files():
    try: docs = [f.name for f in RESUME_DIR.iterdir() if f.is_file() and f.suffix.lower() in ('.pdf', '.docx', '.doc', '.pages')]
    except OSError: return []
    named = [d for d in docs if 'resume' in d.lower()]
    return sorted(named or [d for d in docs if 'cover' not in d.lower()], key=str.lower)
def state():
    with connect() as db:
        applications = [dict(x) for x in db.execute('SELECT id,company,role,status,applied,applied_at,posted_at,url,source,resume,notes,furthest FROM applications ORDER BY COALESCE(NULLIF(applied_at,\'\'),applied) DESC,id DESC')]
    files = resume_files(); resumes = {f: {'resume': f, 'applications': 0, 'interviews': 0} for f in files}
    for a in applications:
        r = resumes.setdefault(a['resume'], {'resume': a['resume'], 'applications': 0, 'interviews': 0})
        r['applications'] += 1; r['interviews'] += a['furthest'] in ('Screen', 'Interview', 'Offer')
    for r in resumes.values(): r['grade'] = grade(r['applications'], r['interviews'])
    order = lambda r: (r['resume'] not in files, not r['resume'], files.index(r['resume']) if r['resume'] in files else -r['applications'])
    return {'applications': applications, 'resumes': sorted(resumes.values(), key=order), 'resume_files': files, 'resume_dir': str(RESUME_DIR), 'stages': STAGES, 'sources': SOURCES}

FILES = {'/': ('index.html', 'text/html; charset=utf-8'), '/theme.js': ('theme.js', 'text/javascript'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def send(self, data, status=200, ctype='application/json'):
        payload = json.dumps(data).encode() if ctype == 'application/json' else data
        self.send_response(status); self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(payload))); self.send_header('Cache-Control', 'no-store'); self.send_header('X-Content-Type-Options', 'nosniff'); self.end_headers(); self.wfile.write(payload)
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if self.headers.get('Host') not in ('localhost:3005', '127.0.0.1:3005'): return self.send({'error': 'Invalid host'}, 403)
        if path == '/health': return self.send({'app': 'simple-job-tracker'})
        if path == '/api/state': return self.send(state())
        if path == '/api/export':
            out = io.StringIO(); writer = csv.writer(out); keys = ['company', 'role', 'status', 'applied', 'applied_at', 'posted_at', 'source', 'resume', 'url', 'notes']
            writer.writerow(['Company', 'Role', 'Status', 'Applied', 'Applied at', 'Posted at', 'Job board', 'Resume', 'Link', 'Notes'])
            for a in state()['applications']:
                writer.writerow([("'"+str(a[k]) if str(a[k]).startswith(('=', '+', '-', '@')) else a[k]) for k in keys])
            return self.send(out.getvalue().encode(), ctype='text/csv; charset=utf-8')
        font = re.fullmatch(r'/fonts/([a-z0-9-]+\.woff2)', path)
        if font and (ROOT/'web/fonts'/font.group(1)).is_file(): return self.send((ROOT/'web/fonts'/font.group(1)).read_bytes(), ctype='font/woff2')
        if path in FILES:
            f, ct = FILES[path]; return self.send((ROOT/'web'/f).read_bytes(), ctype=ct)
        self.send({'error': 'Not found'}, 404)
    def do_POST(self):
        if self.headers.get('Host') not in ('localhost:3005', '127.0.0.1:3005') or self.headers.get('Origin') not in (BASE, 'http://127.0.0.1:3005'): return self.send({'error': 'Invalid origin'}, 403)
        try:
            length = int(self.headers.get('Content-Length', 0))
            if length > 500000: raise ValueError('Request too large')
            d = json.loads(self.rfile.read(length) or '{}')
            if self.path == '/api/import-url': return self.send(import_posting(d.get('url', '')))
            if self.path == '/api/import-captured': return self.send(import_captured(d))
            if self.path == '/api/application': return self.send({'ok': True, 'id': save_application(d)})
            if self.path == '/api/status': set_status(d['id'], d.get('status')); return self.send({'ok': True})
            if self.path == '/api/delete':
                with connect() as db: db.execute('DELETE FROM applications WHERE id=?', (int(d['id']),))
                return self.send({'ok': True})
            self.send({'error': 'Not found'}, 404)
        except PostingError as e: self.send({'error': str(e)}, 400)
        except (ValueError, KeyError, TypeError): self.send({'error': 'Check the fields and try again.'}, 400)
        except Exception: self.send({'error': 'Could not save. Please try again.'}, 500)

if __name__ == '__main__':
    init()
    print('Simple Job Tracker: '+BASE, flush=True)
    ThreadingHTTPServer(('127.0.0.1', 3005), Handler).serve_forever()
