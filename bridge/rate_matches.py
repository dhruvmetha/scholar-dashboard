#!/usr/bin/env python3
"""How strongly each paper matches each of its interests: about / partly / touches (the match_strengths column).

The dashboard scores papers from these (Core fit + context; see SCORING in index.html). New papers get strengths
from the digest runs and Add paper; this rates the ones that don't have them yet. Claude reads each paper's title
and abstract with its matched interests, in batches (no tools, nothing written by Claude); this script checks
the answers and publishes them from the bridge's own copy of the repository, like add_paper.py.

    python3 bridge/rate_matches.py            # rate every paper without strengths, then publish
    python3 bridge/rate_matches.py --dry      # rate, write the copy, don't push (SCHOLAR_ADD_DRY_RUN=1 too)
Answers are cached in ~/.scholar-bridge/rate_cache.json, so a stopped run picks up where it left off.
"""
import concurrent.futures as cf, csv, io, json, os, re, subprocess, sys, tempfile, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import add_paper as ap
from add_paper import CLONE, PAPERS, INTERESTS, Stop

STRENGTHS = ('about', 'partly', 'touches')
CACHE = os.path.join(ap.HOME, 'rate_cache.json')
BATCH, WORKERS = 40, 4
_lock = threading.Lock()

PROMPT = """You rate how strongly research papers match research interests, for a robotics researcher's paper dashboard.
For each paper below, rate EVERY interest listed under it:
- "about": the interest is what the paper is about: its main method, object of study, or what it evaluates or verifies.
- "partly": a substantial part of the paper (a key component, a main experiment domain, a second contribution).
- "touches": it appears but isn't substantial (used as a tool or baseline, mentioned in motivation, a small section).
Judge from the title and abstract. Most papers are "about" one or two of their interests at most.

The interests, for reference:
{glossary}

Reply with ONLY one JSON object mapping each paper id to an object of interest name -> "about" | "partly" | "touches",
using the exact ids and interest names given. No other text.

Papers:
{papers}"""


def parse_strengths(s):
    out = {}
    for part in (s or '').split('|'):
        if '=' in part:
            k, v = part.rsplit('=', 1)
            if v.strip() in STRENGTHS: out[k.strip()] = v.strip()
    return out


def format_strengths(d, order):
    return '|'.join(f'{n}={d[n]}' for n in order if n in d)


def load_cache():
    try:
        with open(CACHE) as f: return json.load(f)
    except Exception: return {}


def save_cache(c):
    with _lock:
        tmp = CACHE + '.tmp'
        with open(tmp, 'w') as f: json.dump(c, f)
        os.replace(tmp, CACHE)


def rate_batch(batch, glossary, model='opus'):
    def one(p):
        abstract = re.sub(r'\s+', ' ', p.get('abstract') or '')[:1400]
        return f"id: {p['id']}\ntitle: {p['title']}\nabstract: {abstract}\ninterests: {' | '.join(p['_mi'])}"
    text = '\n\n'.join(one(p) for p in batch)
    prompt = PROMPT.format(glossary=glossary, papers=text)
    env = dict(os.environ); env['PATH'] = os.path.dirname(ap.claude_bin()) + ':' + env.get('PATH', '/usr/bin:/bin')
    no_mcp = os.path.join(ap.HOME, 'no-mcp.json')
    with tempfile.TemporaryDirectory() as empty:
        r = subprocess.run([ap.claude_bin(), '-p', '--output-format', 'json', '--model', model, '--tools', 'Read', '--allowedTools', 'Read(./**)',
                            '--strict-mcp-config', '--mcp-config', no_mcp, '--setting-sources', ''],
                           input=prompt, capture_output=True, text=True, cwd=empty, env=env, timeout=900)
    try: result = json.loads(r.stdout).get('result') or ''
    except Exception: raise RuntimeError('Claude Code: ' + (r.stderr or r.stdout)[-300:])
    m = re.search(r'\{[\s\S]*\}', result)
    ans = json.loads(m.group(0)) if m else {}
    out = {}
    for p in batch:   # keep only valid answers for this paper's own interests
        got = ans.get(p['id']) or {}
        d = {n: got[n] for n in p['_mi'] if got.get(n) in STRENGTHS}
        if len(d) == len(p['_mi']): out[p['id']] = d
    return out


def rate(ids=None, cb=print):
    ap.fresh_clone()
    _, papers = ap.read_papers()
    with open(os.path.join(CLONE, INTERESTS), newline='', encoding='utf-8') as f:
        interests = [i for i in csv.DictReader(f) if i.get('status') == 'confirmed']
    names = {i['interest_name'] for i in interests}
    glossary = '\n'.join(f"- {i['interest_name']}: {(i.get('notes') or '').strip()} {('(related: ' + i['related_to'] + ')') if i.get('related_to') else ''}".strip() for i in interests)
    todo = []
    for p in papers:
        mi = [n.strip() for n in (p.get('matched_interests') or '').split('|') if n.strip() in names]
        have = parse_strengths(p.get('match_strengths'))
        if mi and (ids is None or p['id'] in ids) and any(n not in have for n in mi): p['_mi'] = mi; todo.append(p)
    cache = load_cache()
    todo = [p for p in todo if not (p['id'] in cache and all(n in cache[p['id']] for n in p['_mi']))]
    cb(f'{len(todo)} papers to rate ({len(cache)} cached)')
    batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
    done = 0
    with cf.ThreadPoolExecutor(WORKERS) as ex:
        futs = {ex.submit(rate_batch, b, glossary): b for b in batches}
        for fut in cf.as_completed(futs):
            try:
                got = fut.result()
                with _lock: cache.update(got)
                save_cache(cache)
                done += len(got)
                cb(f'rated {done}/{len(todo)}')
            except Exception as e:
                cb('a batch failed (it will be retried next run): ' + str(e)[:200])
    return cache


def publish(core, cb=print):
    """Write the strengths, make `core` the Core interests (Related for the rest of today's top level), drop priority."""
    cache = load_cache()
    for attempt in range(3):
        ap.fresh_clone()
        fields, papers = ap.read_papers()
        if 'match_strengths' not in fields: fields.insert(fields.index('matched_interests') + 1, 'match_strengths')
        n = 0
        for p in papers:
            c = cache.get(p['id'])
            if not c: continue
            have = parse_strengths(p.get('match_strengths'))
            mi = [x.strip() for x in (p.get('matched_interests') or '').split('|') if x.strip()]
            merged = {**c, **have}   # anything already there (your own edits) wins
            new = format_strengths(merged, mi)
            if new != (p.get('match_strengths') or ''): p['match_strengths'] = new; n += 1
        with open(os.path.join(CLONE, INTERESTS), newline='', encoding='utf-8') as f:
            r = csv.DictReader(f); ifields = [x for x in r.fieldnames if x != 'priority_level']; irows = list(r)
        changed = []
        if core is not None:
            for i in irows:
                if i.get('status') != 'confirmed': continue
                want = 'definitely' if i['interest_name'] in core else ('probably' if i.get('relevance_mapping') == 'definitely' else i.get('relevance_mapping'))
                if want != i.get('relevance_mapping'): changed.append(f"{i['interest_name']}: {i.get('relevance_mapping')} -> {want}"); i['relevance_mapping'] = want
        write(PAPERS, fields, papers)
        write(INTERESTS, ifields, irows)
        ap.git('add', PAPERS, INTERESTS)
        if ap.git('diff', '--cached', '--quiet', check=False).returncode == 0: return {'papers': 0, 'interests': []}
        ap.git('commit', '-q', '-m', f'Scoring: match strengths on {n} papers; interests on one scale (Core/Related/Peripheral), priority dropped')
        rr = ap.git('push', *(['--dry-run'] if ap.DRY_RUN else []), f'https://x-access-token:{ap.gh_token()}@{ap.REMOTE}', 'HEAD:main', check=False)
        if rr.returncode == 0: return {'papers': n, 'interests': changed}
        if attempt == 2: raise RuntimeError('push failed: ' + (rr.stderr or '')[-300:].replace(ap.gh_token(), '***'))


def write(name, fields, rows):
    path = os.path.join(CLONE, name)
    with open(path, 'rb') as f: nl = '\r\n' if b'\r\n' in f.read(20000) else '\n'
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator=nl, extrasaction='ignore')
    w.writeheader()
    for r in rows: w.writerow({k: r.get(k) or '' for k in fields})
    with open(path, 'w', encoding='utf-8', newline='') as f: f.write(buf.getvalue())


CORE = ['Data-driven verification', 'Verification of visuomotor policies', 'Latent-space safety analysis',
        'Runtime verification of learned policies', 'Rare-event failure probability estimation']

if __name__ == '__main__':
    if '--dry' in sys.argv: ap.DRY_RUN = True
    rate()
    if '--rate-only' not in sys.argv:
        out = publish(CORE)
        print(f"strengths on {out['papers']} papers; interests: {out['interests']}")
