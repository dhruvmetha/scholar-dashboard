#!/usr/bin/env python3
"""Scholar Dashboard <-> Claude Code bridge.

A small local server that lets the dashboard (the GitHub Pages site, or scholar.localhost) chat with Claude
through Claude Code on this laptop: one Claude Code session per paper, streamed back to the page.

Safety:
  * listens on 127.0.0.1 only, and answers only the dashboard's own origins;
  * every request except /health and /pair needs a pairing token, issued only after you click Allow in a
    macOS dialog on this laptop;
  * Claude runs with no shell, no connectors or plugins, and may read only files in this bridge's work folder
    (the paper PDFs and figures the dashboard sends); it may search and fetch from the web.
  * Adding a paper (the dashboard's Add paper box, /paper/add): Claude only researches it, read-only, in the bridge's
    own copy of the repository (~/.scholar-bridge/repo); add_paper.py checks what it returns and commits and pushes
    just that row (and its link-preview page) from that copy. Your working copy is never touched.

Everything lives in ~/.scholar-bridge:  token, sessions.json, chats/<paper>.json (what the dashboard shows),
work/ (Claude Code's working folder: papers/<paper>.pdf, attachments/). The Claude Code sessions themselves
are ordinary ones: `cd ~/.scholar-bridge/work && claude --resume` lists them.
"""
import base64, json, os, re, secrets, shutil, subprocess, sys, threading, time, urllib.request, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import add_paper
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get('SCHOLAR_BRIDGE_PORT', '7823'))
ORIGINS = {'https://www.sumanthtangirala.com', 'https://sumanthtangirala.com', 'http://scholar.localhost', 'http://localhost'}
HOME = os.path.expanduser(os.environ.get('SCHOLAR_BRIDGE_HOME', '~/.scholar-bridge'))   # override: a separate test copy
WORK = os.path.join(HOME, 'work')
CHATS = os.path.join(HOME, 'chats')
TOKEN_FILE = os.path.join(HOME, 'token')
SESSIONS_FILE = os.path.join(HOME, 'sessions.json')
NO_MCP = os.path.join(HOME, 'no-mcp.json')
MODELS = {'opus': 'opus', 'sonnet': 'sonnet', 'haiku': 'haiku'}
EFFORTS = {'low', 'medium', 'high', 'xhigh', 'max'}   # anything else: Claude Code's default
VERSION = 2   # 2: /paper/add

for d in (HOME, WORK, CHATS, os.path.join(WORK, 'papers'), os.path.join(WORK, 'attachments')):
    os.makedirs(d, exist_ok=True)
if not os.path.exists(NO_MCP):
    with open(NO_MCP, 'w') as f: json.dump({'mcpServers': {}}, f)

_lock = threading.Lock()
_running = {}   # paper id -> subprocess.Popen
_add = {'job': None, 'proc': None}   # the paper being added (one at a time); the page polls GET /paper/add


def start_add(text, star):
    job = {'id': uuid.uuid4().hex[:12], 'state': 'running', 'stage': 'Starting…', 'input': text[:300], 'started': time.time()}
    _add['job'] = job

    def stage(s): job['stage'] = s
    def run():
        try:
            out = add_paper.add(text, star=star, cb=stage, on_proc=lambda p: _add.__setitem__('proc', p))
            job.update(state='done', added=out['added'], existing=out['existing'])
        except add_paper.Stop as e:
            job.update(state='stopped', message=str(e))
        except Exception as e:
            job.update(state='error', message=(str(e) or 'failed')[-400:])
        finally:
            _add['proc'] = None; job['ended'] = time.time()
    threading.Thread(target=run, daemon=True).start()
    return job


def claude_bin():
    for p in (shutil.which('claude'), os.path.expanduser('~/.local/bin/claude'), '/opt/homebrew/bin/claude', '/usr/local/bin/claude'):
        if p and os.path.exists(p): return p
    return 'claude'


def read_json(path, default):
    try:
        with open(path) as f: return json.load(f)
    except Exception: return default


def write_json(path, obj):
    tmp = path + '.tmp'
    with open(tmp, 'w') as f: json.dump(obj, f)
    os.replace(tmp, path)


def token():
    try:
        with open(TOKEN_FILE) as f: return f.read().strip()
    except Exception: return ''


def safe_id(pid):
    return re.sub(r'[^A-Za-z0-9._-]', '_', pid or '')[:120]


def chat_file(pid): return os.path.join(CHATS, safe_id(pid) + '.json')


def load_chat(pid):
    return read_json(chat_file(pid), {'paper': pid, 'session': None, 'model': 'opus', 'messages': []})


def archive_current(pid):
    """Keep the current conversation as an earlier one (a unique name, so nothing is ever overwritten)."""
    ts = int(time.time())
    while os.path.exists(chat_file(pid)[:-5] + f'.{ts}.json'): ts += 1
    os.replace(chat_file(pid), chat_file(pid)[:-5] + f'.{ts}.json')


def chat_list(pid):
    """This paper's conversations: the current one and earlier ones (kept when you start a new chat)."""
    base, out = safe_id(pid), []
    for f in os.listdir(CHATS):
        if f == base + '.json': key = 'current'
        elif f.startswith(base + '.') and f.endswith('.json') and f[len(base) + 1:-5].isdigit(): key = f[len(base) + 1:-5]
        else: continue
        msgs = read_json(os.path.join(CHATS, f), {}).get('messages') or []
        if not msgs: continue
        first = next((m.get('text') for m in msgs if m.get('role') == 'user' and m.get('text')), '') or 'Figure or passage'
        out.append({'id': key, 'title': first[:140], 'count': len(msgs), 'updated': msgs[-1].get('ts') or 0})
    return sorted(out, key=lambda c: -c['updated'])


def forget_paper(pid):
    """Everything kept for a paper: its chats, the PDF and figure copies, and Claude Code's own transcripts of them."""
    base = safe_id(pid)
    if not base: return 0
    sessions, gone = set(), 0
    for f in os.listdir(CHATS):
        if f == base + '.json' or (f.startswith(base + '.') and f.endswith('.json') and f[len(base) + 1:-5].isdigit()):
            s = read_json(os.path.join(CHATS, f), {}).get('session')
            if s and re.fullmatch(r'[0-9a-f-]{36}', s): sessions.add(s)
            os.remove(os.path.join(CHATS, f)); gone += 1
    for path in [os.path.join(WORK, 'papers', base + '.pdf')] + [os.path.join(WORK, 'attachments', f) for f in os.listdir(os.path.join(WORK, 'attachments')) if f.startswith(base + '-')]:
        if os.path.exists(path): os.remove(path); gone += 1
    projects = os.path.expanduser('~/.claude/projects')
    for d in (os.listdir(projects) if os.path.isdir(projects) else []):
        for s in sessions:
            for path in (os.path.join(projects, d, s + '.jsonl'), os.path.join(projects, d, s)):
                if os.path.isfile(path): os.remove(path); gone += 1
                elif os.path.isdir(path): shutil.rmtree(path, ignore_errors=True); gone += 1
    return gone


def ask_permission(code):
    """A native dialog on this laptop: the only way to get a token."""
    script = ('display dialog "Scholar Dashboard wants to chat with Claude through Claude Code on this Mac.\\n\\n'
              f'Code shown in the page: {code}" with title "Scholar Dashboard" buttons {{"Don\'t Allow", "Allow"}} '
              'default button "Allow" cancel button "Don\'t Allow" with icon note giving up after 60')
    try:
        r = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=70)
        return r.returncode == 0 and 'Allow' in r.stdout and 'gave up:true' not in r.stdout
    except Exception:
        return False


SYSTEM = """You are a research assistant inside the user's paper-reading app. The user is reading one paper; its full text is given in <paper> in the conversation (page-marked), and the PDF is at ./papers/{pdf} if you need to look at a figure, table or equation layout (use Read with the pages you need). Images the user attaches are saved under ./attachments/ and named in their message.

Each message may start with <context>: the user's current highlights, comments and notes on this paper (they change as they read), their research interests, and sometimes other papers they @-mentioned. Use them; don't repeat them back.

Citing the paper: whenever you point to something in the paper, cite it with its exact words in this form: [[p.N "exact words from the paper"]] (N = page). The quote must be contiguous and verbatim (no ellipses, no paraphrase), a phrase to a sentence long, with symbols as they appear in the text. The app shows each citation only as a small clickable pill (page number and a few words), so the reader cannot read its words: it is a footnote marker, never part of your prose. Every sentence, list item and table cell must say everything on its own, as if the citation were deleted; put the citation right after the claim it supports. Wrong: "Predicates live on [[p.2 "the low-dimensional state space"]]" (reads as "Predicates live on p.2 the low-dime…"). Right: "Predicates are defined over a low-dimensional state space [[p.2 "the low-dimensional state space"]]." A citation never replaces words, and a table cell never consists of only a citation. Tables are where this slips most: wrong "| $\\phi$ | The sensor. It [[p.4 "is the observation function"]]. |", right "| $\\phi$ | The sensor: maps the true state to what the sensors observe [[p.4 "is the observation function"]]. |". Before sending, reread each sentence with its citations removed; if any is incomplete, rewrite it. Use [[p.N "..."]] only for the paper being read (its pills jump within it); cite other papers, including ones the user @-mentions, in plain text by title or author, with a page if useful.

Other papers: the user's library is in ./library.tsv (tab-separated, one paper per line: id, title, authors, date, venue, topics, one-line summary, and flags such as starred, read, notes). When they refer to another paper by description ("the Ames backup-CBF paper", "the conformal STL one I read last month"), search that file with Grep (try a few keywords) to identify it. If more than one could fit, ask them with a short numbered list of titles. Once you know which paper(s) they mean, reply with only one line per paper, ```paper <id>```, and nothing else: the app then sends you that paper's text and the user's own notes on it, and you continue answering their question. Papers they @-mention arrive the same way, in <other-paper>.

Notes and highlights: never add to the user's notes unless they explicitly ask you to. When they do, put each note in a fenced block ```note ... ``` (Markdown; you may cite with [[p.N "..."]] inside), and each highlight as ```highlight p.N color "exact words"``` (color is one of orange, green, blue, red, purple). The app saves them for the user.

Be direct and concise; use Markdown and $math$ / $$math$$. The chat is a narrow side panel (often under 400px): keep tables to about three columns of short cells, and put citations in the text after the table rather than inside its cells. Say when something is your inference rather than in the paper.{profile}"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        pass

    # ---- plumbing ----
    def origin_ok(self):
        return self.headers.get('Origin', '') in ORIGINS

    def cors(self):
        o = self.headers.get('Origin', '')
        if o in ORIGINS:
            self.send_header('Access-Control-Allow-Origin', o)
            self.send_header('Access-Control-Allow-Headers', 'content-type, authorization')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Private-Network', 'true')
            self.send_header('Vary', 'Origin')

    def reply(self, status, obj):
        body = json.dumps(obj).encode()
        self.send_response(status); self.cors()
        self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def body(self):
        n = int(self.headers.get('Content-Length') or 0)
        return json.loads(self.rfile.read(n) or b'{}') if n else {}

    def authed(self):
        t = token()
        return bool(t) and secrets.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + t)

    def do_OPTIONS(self):
        self.send_response(204 if self.origin_ok() else 403); self.cors()
        self.send_header('Content-Length', '0'); self.end_headers()

    def do_GET(self):
        if not self.origin_ok(): return self.reply(403, {'error': 'origin'})
        path, _, q = self.path.partition('?')
        params = dict(p.split('=', 1) for p in q.split('&') if '=' in p)
        if path == '/health':
            return self.reply(200, {'ok': True, 'version': VERSION, 'paired': self.authed()})
        if not self.authed(): return self.reply(401, {'error': 'not paired'})
        if path == '/chats':
            return self.reply(200, {'chats': chat_list(urllib.request.unquote(params.get('paper', '')))})
        if path == '/paper/add':   # the paper being (or last) added
            return self.reply(200, {'job': _add['job']})
        if path == '/chat':
            pid = urllib.request.unquote(params.get('paper', ''))
            c = load_chat(pid)
            return self.reply(200, {'messages': c['messages'], 'model': c.get('model', 'opus'), 'running': pid in _running, 'fresh': not c.get('session')})
        return self.reply(404, {'error': 'not found'})

    def do_POST(self):
        if not self.origin_ok(): return self.reply(403, {'error': 'origin'})
        path = self.path.partition('?')[0]
        if path == '/pair':
            code = re.sub(r'\D', '', str(self.body().get('code', '')))[:6]   # digits only: it goes into the dialog's script
            if not ask_permission(code): return self.reply(403, {'error': 'declined'})
            t = token() or secrets.token_urlsafe(32)
            with open(TOKEN_FILE, 'w') as f: f.write(t)
            os.chmod(TOKEN_FILE, 0o600)
            return self.reply(200, {'token': t})
        if not self.authed(): return self.reply(401, {'error': 'not paired'})
        data = self.body()
        if path == '/chat/new':
            pid = data.get('paper', '')
            c = load_chat(pid)
            if c['messages']: archive_current(pid)   # keep the old conversation, start a fresh one
            write_json(chat_file(pid), {'paper': pid, 'session': None, 'model': c.get('model', 'opus'), 'messages': []})
            return self.reply(200, {'ok': True})
        if path == '/chat/switch':   # go back to an earlier conversation; the current one is kept
            pid, key = data.get('paper', ''), str(data.get('id', ''))
            if pid in _running: return self.reply(409, {'error': 'busy'})
            target = chat_file(pid)[:-5] + f'.{key}.json'
            if not key.isdigit() or not os.path.exists(target): return self.reply(404, {'error': 'no such chat'})
            cur = chat_file(pid)
            if load_chat(pid)['messages']: archive_current(pid)
            os.replace(target, cur)
            return self.reply(200, {'ok': True})
        if path == '/chat/stop':
            p = _running.get(data.get('paper', ''))
            if p: p.terminate()
            return self.reply(200, {'ok': True})
        if path == '/chat/send':
            return self.send_chat(data)
        if path == '/paper/forget':   # an uploaded paper was removed: keep nothing of it
            pid = data.get('paper', '')
            if not re.fullmatch(r'up-[0-9a-f]{12}', pid): return self.reply(400, {'error': 'only uploaded papers'})
            if pid in _running: _running[pid] and _running[pid].terminate()
            return self.reply(200, {'ok': True, 'removed': forget_paper(pid)})
        if path == '/paper/add':   # add a paper you chose: research (Claude, read-only), then publish (add_paper.py)
            text = str(data.get('input', '')).strip()[:2000]
            if not text: return self.reply(400, {'error': 'input'})
            with _lock:
                j = _add['job']
                if j and j['state'] == 'running': return self.reply(409, {'error': 'busy', 'job': j})
                return self.reply(200, {'job': start_add(text, bool(data.get('star')))})
        if path == '/paper/add/stop':
            p = _add['proc']
            if p: p.terminate()
            return self.reply(200, {'ok': True})
        if path == '/library':   # the user's paper list, for finding papers they describe (no notes in it)
            with open(os.path.join(WORK, 'library.tsv'), 'w') as f: f.write(str(data.get('tsv', ''))[:3_000_000])
            return self.reply(200, {'ok': True})
        return self.reply(404, {'error': 'not found'})

    # ---- one turn: run Claude Code for this paper's session and stream its reply ----
    def send_chat(self, d):
        pid = d.get('paper', '')
        if not pid: return self.reply(400, {'error': 'paper'})
        with _lock:
            if pid in _running: return self.reply(409, {'error': 'busy'})
            _running[pid] = None
        try:
            c = load_chat(pid)
            model = d.get('model') if d.get('model') in MODELS else c.get('model', 'opus')
            fresh = not c.get('session')
            session = c.get('session') or str(uuid.uuid4())
            pdf_name = safe_id(pid) + '.pdf'
            pdf_path = os.path.join(WORK, 'papers', pdf_name)
            if fresh and (d.get('pdfBase64') or not os.path.exists(pdf_path)):   # a file you gave may have changed since
                self.fetch_pdf(d.get('pdfUrl'), d.get('pdfBase64'), pdf_path)
            names = []
            for i, img in enumerate(d.get('images') or []):   # figure crops: saved where Claude can Read them
                m = re.match(r'data:image/(png|jpeg);base64,(.+)', img or '')
                if not m: continue
                name = f'{safe_id(pid)}-{int(time.time())}-{i}.{m.group(1)}'
                with open(os.path.join(WORK, 'attachments', name), 'wb') as f: f.write(base64.b64decode(m.group(2)))
                names.append('./attachments/' + name)
            parts = []
            if fresh and d.get('paperText'): parts.append('<paper>\n' + d['paperText'] + '\n</paper>')
            if d.get('context'): parts.append('<context>\n' + d['context'] + '\n</context>')
            if names: parts.append('Attached images (Read them): ' + ', '.join(names))
            parts.append(d.get('message', ''))
            prompt = '\n\n'.join(parts)
            system = SYSTEM.format(pdf=pdf_name if os.path.exists(pdf_path) else '(none)', profile=('\n\nAbout the user: ' + d['profile']) if d.get('profile') else '')
            args = [claude_bin(), '-p', '--output-format', 'stream-json', '--verbose', '--include-partial-messages',
                    '--model', MODELS[model], '--system-prompt', system,
                    *(['--effort', d['effort']] if d.get('effort') in EFFORTS else []),
                    '--tools', 'Read', 'Grep', 'Glob', 'WebSearch', 'WebFetch',
                    '--allowedTools', 'Read(./**)', 'Grep(./**)', 'Glob(./**)', 'WebSearch', 'WebFetch',   # files: this folder only
                    '--strict-mcp-config', '--mcp-config', NO_MCP, '--setting-sources', '',
                    ('--session-id' if fresh else '--resume'), session]
            env = dict(os.environ); env['PATH'] = os.path.dirname(claude_bin()) + ':' + env.get('PATH', '/usr/bin:/bin')
            proc = subprocess.Popen(args, cwd=WORK, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            _running[pid] = proc
            proc.stdin.write(prompt.encode()); proc.stdin.close()

            now = time.time()
            c['messages'].append({'role': 'user', 'text': d.get('display', d.get('message', '')), 'quotes': d.get('quotes') or [], 'images': len(names), 'mentions': d.get('mentions') or [], 'auto': bool(d.get('auto')), 'ts': now})   # what you typed, not the wrapped prompt
            c.update(session=session, model=model)
            write_json(chat_file(pid), c)

            self.send_response(200); self.cors()
            self.send_header('Content-Type', 'application/x-ndjson'); self.send_header('Cache-Control', 'no-store')
            self.send_header('Transfer-Encoding', 'chunked'); self.end_headers()

            def emit(obj):
                b = (json.dumps(obj) + '\n').encode()
                try:
                    self.wfile.write(f'{len(b):x}\r\n'.encode() + b + b'\r\n'); self.wfile.flush()
                except Exception:
                    pass

            text, result = '', None
            for line in proc.stdout:
                try: e = json.loads(line)
                except Exception: continue
                t = e.get('type')
                if t == 'stream_event':
                    ev = e.get('event') or {}
                    if ev.get('type') == 'content_block_delta' and (ev.get('delta') or {}).get('type') == 'text_delta':
                        chunk = ev['delta'].get('text', ''); text += chunk; emit({'t': 'text', 'v': chunk})
                    elif ev.get('type') == 'content_block_start' and (ev.get('content_block') or {}).get('type') in ('tool_use', 'server_tool_use'):
                        emit({'t': 'tool', 'v': ev['content_block'].get('name')})
                    elif ev.get('type') == 'message_start' and text and not text.endswith('\n\n'):
                        text += '\n\n'; emit({'t': 'text', 'v': '\n\n'})   # a new assistant message after a tool call
                elif t == 'result':
                    result = e
            proc.wait()
            err = '' if result else (proc.stderr.read().decode(errors='replace')[-600:] or 'stopped')
            if result and result.get('result') and not text: text = result['result']
            c = load_chat(pid)
            if text: c['messages'].append({'role': 'assistant', 'text': text, 'ts': time.time(), 'model': model})
            elif fresh: c['session'] = None   # the session never started: the next message starts it again
            write_json(chat_file(pid), c)
            emit({'t': 'done', 'session': session, 'error': err if not text else '', 'cost': (result or {}).get('total_cost_usd')})
            try: self.wfile.write(b'0\r\n\r\n'); self.wfile.flush()
            except Exception: pass
        finally:
            _running.pop(pid, None)

    def fetch_pdf(self, url, b64, path):
        try:
            if b64:
                with open(path, 'wb') as f: f.write(base64.b64decode(b64))
            elif url and url.startswith('https://'):
                req = urllib.request.Request(url, headers={'User-Agent': 'ScholarDashboard/1'})
                with urllib.request.urlopen(req, timeout=30) as r, open(path, 'wb') as f: shutil.copyfileobj(r, f)
        except Exception:
            try: os.remove(path)
            except Exception: pass


if __name__ == '__main__':
    print(f'Scholar bridge on http://127.0.0.1:{PORT} (claude: {claude_bin()})', flush=True)
    ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
