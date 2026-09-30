#!/usr/bin/env python3
"""Add papers you chose to the Scholar Dashboard database.

Two steps, kept apart on purpose:
  1. research (Claude, following bridge/add_paper.md): find the paper, describe it for you, and return rows as JSON.
     Claude gets no shell and cannot write files; it reads the databases and searches/fetches the web.
  2. publish (this script): check every field, drop duplicates, make the id, append the row, refresh the link-preview
     pages, commit and push. This happens in the bridge's own copy of the repository (~/.scholar-bridge/repo), never
     in your working copy, so nothing you are editing is ever committed along with it.

Used by the bridge (the dashboard's Add paper box) and from the command line:
    python3 bridge/add_paper.py "https://arxiv.org/abs/2609.01234"      # research + publish
    python3 bridge/add_paper.py --rows rows.json                          # publish rows you (or Claude Code) made
"""
import csv, datetime, io, json, os, re, shutil, subprocess, sys, unicodedata

REPO_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # this checkout: its token and instructions
HOME = os.path.expanduser(os.environ.get('SCHOLAR_BRIDGE_HOME', '~/.scholar-bridge'))
CLONE = os.path.join(HOME, 'repo')
REMOTE = 'github.com/sumanth-tangirala/scholar-dashboard.git'
DRY_RUN = os.environ.get('SCHOLAR_ADD_DRY_RUN') == '1'   # everything but the push (git push --dry-run): for testing
PAPERS, INTERESTS, GROUPS = 'papers_database.csv', 'interests_database.csv', 'groups_database.csv'
STOP = set('a an the for of with via using in on to and or from by is are be can will has have not but as at new novel '
           'towards toward its it this that these we our into onto over under than how what when where which do does'.split())
PARTICLES = {'van', 'von', 'de', 'der', 'den', 'da', 'di', 'du', 'del', 'della', 'le', 'la', 'dos', 'das', 'ter', 'ten'}
TEXT_FIELDS = ('title', 'authors', 'venue', 'publishing_date', 'url', 'pdf_url', 'abstract', 'headline', 'summary', 'notes')


class Stop(Exception):
    """A reason to add nothing, worded for the user."""


def log(stage, cb):
    if cb: cb(stage)


# ---------- the bridge's own copy of the repository ----------
def gh_token():
    with open(os.path.join(REPO_SRC, '.github_token')) as f: return f.read().strip()


def git(*args, check=True):
    r = subprocess.run(['git', *args], cwd=CLONE, capture_output=True, text=True, timeout=120)
    if check and r.returncode:
        raise RuntimeError(('git ' + args[0] + ' failed: ' + (r.stderr or r.stdout)[-400:]).replace(gh_token(), '***'))
    return r


def fresh_clone():
    """The copy, exactly as GitHub has it now (it is the bridge's alone, so it is simply reset)."""
    url = f'https://x-access-token:{gh_token()}@{REMOTE}'
    if not os.path.isdir(os.path.join(CLONE, '.git')):
        os.makedirs(HOME, exist_ok=True)
        r = subprocess.run(['git', 'clone', '--depth', '20', url, CLONE], capture_output=True, text=True, timeout=300)
        if r.returncode: raise RuntimeError('clone failed: ' + (r.stderr or '')[-300:].replace(gh_token(), '***'))
        git('remote', 'set-url', 'origin', 'https://' + REMOTE)   # the token is never stored in the copy
        git('config', 'user.name', 'Scholar Dashboard Bot'); git('config', 'user.email', 'bot@scholar-dashboard.local')
    git('fetch', '--force', '--depth', '20', url, 'main:refs/remotes/origin/main')
    git('checkout', '-q', '-B', 'main', 'origin/main')
    git('reset', '-q', '--hard', 'origin/main'); git('clean', '-qfd')


# ---------- reading the databases ----------
def read_papers():
    with open(os.path.join(CLONE, PAPERS), newline='', encoding='utf-8') as f:
        r = csv.DictReader(f)
        return r.fieldnames, list(r)


def confirmed(file, key, delim=','):
    with open(os.path.join(CLONE, file), newline='', encoding='utf-8') as f:
        return {row[key].strip() for row in csv.DictReader(f, delimiter=delim) if (row.get('status') or '').strip() == 'confirmed' and row.get(key)}


def norm_title(t): return re.sub(r'[^a-z0-9]', '', (t or '').lower())
def arxiv_ids(s): return set(m.split('v')[0] for m in re.findall(r'(\d{4}\.\d{4,5}(?:v\d+)?)', s or ''))
def dois(s): return set(d.lower().rstrip('.)') for d in re.findall(r'10\.\d{4,9}/[^\s"\'<>|,]+', s or ''))


def existing_match(rows, p):
    """The paper itself, never its id: same arXiv id, DOI or title (hidden rows count: you hid them on purpose)."""
    ax = arxiv_ids(' '.join([p.get('arxiv_id', ''), p.get('url', ''), p.get('pdf_url', '')]))
    dx = dois(' '.join([p.get('doi', ''), p.get('url', '')]))
    t = norm_title(p.get('title'))
    for r in rows:
        blob = ' '.join([r.get('url', ''), r.get('pdf_url', '')])
        if (ax and ax & arxiv_ids(blob)) or (dx and dx & dois(blob)) or (t and len(t) > 12 and norm_title(r.get('title')) == t):
            return r
    return None


def lookup_input(rows, text):
    """A link, arXiv id or DOI already in the database: found without asking Claude."""
    ax, dx = arxiv_ids(text), dois(text)
    if not ax and not dx: return None
    for r in rows:
        blob = ' '.join([r.get('url', ''), r.get('pdf_url', '')])
        if (ax & arxiv_ids(blob)) or (dx & dois(blob)): return r
    return None


# ---------- the id: {lastname}-{year}-{keyword1}-{keyword2} ----------
def ascii_word(s): return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower())


def make_id(p, taken):
    first = (p.get('authors') or '').split(',')[0].strip()
    toks = [t for t in re.split(r'\s+', first) if t]
    last = 'unknown'
    if toks and first.lower() != 'not specified':
        i = len(toks) - 1
        while i > 0 and toks[i - 1].lower() in PARTICLES: i -= 1
        last = ascii_word(''.join(toks[i:])) or 'unknown'
    year = (re.search(r'(\d{4})', p.get('publishing_date') or '') or re.search(r'(\d{4})', datetime.date.today().isoformat())).group(1)
    words = [ascii_word(w) for w in re.split(r'[\s\-–—:/]+', p.get('title') or '')]
    keys = [w for w in words if w and w not in STOP][:2] or ['paper']
    base = '-'.join([last, year, *keys])
    pid, n = base, 2
    while pid in taken: pid, n = f'{base}-{n}', n + 1
    return pid


# ---------- checking what Claude returned ----------
def clean_row(p, interests, groups):
    out = {k: re.sub(r'[ \t]+', ' ', str(p.get(k) or '')).strip() for k in TEXT_FIELDS}
    for k in ('title', 'authors', 'abstract', 'headline'):
        if not out[k]: raise Stop(f'The paper came back without its {k}; nothing was added. Try again, or give its arXiv or DOI link.')
    for k in ('url', 'pdf_url'):
        if out[k] and not re.match(r'https://', out[k]): out[k] = ''
    if not out['url']: raise Stop('No permanent link was found for the paper; nothing was added.')
    mi = [m for m in (p.get('matched_interests') or []) if isinstance(m, str) and m.strip() in interests]
    tg = [g for g in (p.get('theme_groups') or []) if isinstance(g, str) and g.strip() in groups and g.strip().lower() != 'other'][:3]
    try: res = max(-1, min(1, int(p.get('residual_score') or 0)))
    except Exception: res = 0
    tier = p.get('relevance_tier') if p.get('relevance_tier') in ('definitely', 'probably', 'mildly') else 'mildly'
    out.update(matched_interests='|'.join(dict.fromkeys(m.strip() for m in mi)), theme_groups='|'.join(dict.fromkeys(g.strip() for g in tg)),
               residual_score=str(res), relevance_tier=tier, notes=out['notes'] or 'Added by you.',
               arxiv_id=str(p.get('arxiv_id') or ''), doi=str(p.get('doi') or ''))
    return out


# ---------- publishing ----------
def publish(papers, star=False, lists=None, cb=None):
    """Append the new papers (duplicates are reported, not added), then commit and push. Retries from a fresh copy if
    someone else pushed meanwhile. Returns {'added': [rows], 'existing': [ids]}."""
    for attempt in range(3):
        log('Saving to your database…', cb)
        fresh_clone()
        fields, rows = read_papers()
        interests, groups = confirmed(INTERESTS, 'interest_name'), confirmed(GROUPS, 'group_name', '|')
        taken = {r['id'] for r in rows}
        added, existing = [], []
        for p in papers:
            row = clean_row(p, interests, groups)
            same = existing_match(rows + added, row)
            if same: existing.append(same['id']); continue
            row.update(id=make_id(row, taken), date_found=datetime.date.today().isoformat(), source_mode='manual',
                       is_read='false', is_starred='true' if star else 'false', user_lists='|'.join(lists or []))
            taken.add(row['id']); added.append(row)
        if not added: return {'added': [], 'existing': existing}
        path = os.path.join(CLONE, PAPERS)
        with open(path, 'rb') as f: data = f.read()
        nl = '\r\n' if b'\r\n' in data[:20000] else '\n'
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=fields, extrasaction='ignore', lineterminator=nl)
        for r in added: w.writerow({k: r.get(k, '') for k in fields})
        with open(path, 'ab') as f:
            if data and not data.endswith(b'\n'): f.write(nl.encode())
            f.write(buf.getvalue().encode('utf-8'))
        subprocess.run([sys.executable, os.path.join(CLONE, 'make_share_pages.py')], cwd=CLONE, capture_output=True, timeout=120)
        git('add', PAPERS); git('add', '-A', 'p')
        titles = '; '.join(r['title'][:60] for r in added)
        git('commit', '-q', '-m', f'Add paper by hand: {titles}')
        log('Publishing…', cb)
        r = git('push', *(['--dry-run'] if DRY_RUN else []), f'https://x-access-token:{gh_token()}@{REMOTE}', 'HEAD:main', check=False)
        if r.returncode == 0: return {'added': added, 'existing': existing}
        if attempt == 2: raise RuntimeError('push failed: ' + (r.stderr or '')[-300:].replace(gh_token(), '***'))
    return {'added': [], 'existing': []}


# ---------- research (Claude Code, read-only) ----------
def claude_bin():
    for p in (shutil.which('claude'), os.path.expanduser('~/.local/bin/claude'), '/opt/homebrew/bin/claude', '/usr/local/bin/claude'):
        if p and os.path.exists(p): return p
    return 'claude'


def research(text, cb=None, model='opus', on_proc=None):
    with open(os.path.join(REPO_SRC, 'bridge', 'add_paper.md')) as f: instructions = f.read()
    no_mcp = os.path.join(HOME, 'no-mcp.json')
    if not os.path.exists(no_mcp):
        with open(no_mcp, 'w') as f: json.dump({'mcpServers': {}}, f)
    args = [claude_bin(), '-p', '--output-format', 'stream-json', '--verbose', '--model', model,
            '--append-system-prompt', instructions,
            '--tools', 'Read', 'Grep', 'Glob', 'WebSearch', 'WebFetch',
            '--allowedTools', 'Read(./**)', 'Grep(./**)', 'Glob(./**)', 'WebSearch', 'WebFetch',   # files: the copy only, read-only
            '--strict-mcp-config', '--mcp-config', no_mcp, '--setting-sources', '']
    env = dict(os.environ); env['PATH'] = os.path.dirname(claude_bin()) + ':' + env.get('PATH', '/usr/bin:/bin')
    proc = subprocess.Popen(args, cwd=CLONE, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True)
    if on_proc: on_proc(proc)
    proc.stdin.write('Input: ' + text.strip() + '\n\nFollow the instructions for adding a paper and answer with the JSON block only.')
    proc.stdin.close()
    result = ''
    for line in proc.stdout:
        try: e = json.loads(line)
        except Exception: continue
        if e.get('type') == 'assistant':
            for b in (e.get('message') or {}).get('content') or []:
                if b.get('type') in ('tool_use', 'server_tool_use'):
                    log({'WebSearch': 'Searching for the paper…', 'WebFetch': 'Reading its page…'}.get(b.get('name'), 'Checking your interests…'), cb)
        elif e.get('type') == 'result':
            result = e.get('result') or ''
    proc.wait()
    if proc.returncode and not result: raise RuntimeError('Claude Code stopped: ' + proc.stderr.read()[-300:])
    m = re.search(r'```(?:json)?\s*(\{[\s\S]*\})\s*```', result) or re.search(r'(\{[\s\S]*\})', result)
    if not m: raise Stop('Claude could not describe the paper; nothing was added.')
    try: ans = json.loads(m.group(1))
    except Exception: raise Stop('Claude’s answer could not be read; nothing was added.')
    if ans.get('stop'):
        msg = ans.get('message') or {'private': 'This paper has no public version, so it was not added. Use Library, Upload PDF instead, where it stays private.', 'not found': 'The paper could not be found.'}.get(ans['stop'], 'Nothing was added.')
        if ans.get('candidates'): msg += ' Did you mean: ' + '; '.join(ans['candidates'][:5]) + '?'
        raise Stop(msg)
    papers = ans.get('papers') or []
    if not papers: raise Stop('No paper was found for that; nothing was added.')
    return papers


def add(text, star=False, lists=None, cb=None, on_proc=None):
    """The whole thing, for one input. Returns {'added': [rows], 'existing': [ids]}; raises Stop with a message."""
    text = (text or '').strip()
    if not text: raise Stop('Give a link, DOI, arXiv id or title.')
    log('Checking your database…', cb)
    fresh_clone()
    _, rows = read_papers()
    hit = lookup_input(rows, text)
    if hit: return {'added': [], 'existing': [hit['id']]}
    log('Finding the paper…', cb)
    papers = research(text, cb, on_proc=on_proc)
    return publish(papers, star, lists, cb)


if __name__ == '__main__':
    a = sys.argv[1:]
    try:
        if a[:1] == ['--rows']:
            with open(a[1]) as f: data = json.load(f)
            out = publish(data.get('papers', data) if isinstance(data, dict) else data, cb=print)
        elif a:
            out = add(' '.join(a), cb=print)
        else:
            print(__doc__); sys.exit(2)
    except Stop as e:
        print('Not added: ' + str(e)); sys.exit(1)
    for r in out['added']: print(f"Added {r['id']}: {r['title']}\n  https://www.sumanthtangirala.com/scholar-dashboard/#paper/{r['id']}")
    for i in out['existing']: print(f'Already in the database: {i}\n  https://www.sumanthtangirala.com/scholar-dashboard/#paper/{i}')
