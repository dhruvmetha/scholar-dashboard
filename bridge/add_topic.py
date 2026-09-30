#!/usr/bin/env python3
"""Tag the existing papers with a new topic (a group in groups_database.csv).

When a topic is created or approved, only papers found after that would get it; this puts it on the papers already
in the database. Same split as add_paper.py:
  1. research (Claude, following bridge/add_topic.md, read-only): which papers belong in the topic;
  2. publish (this script): check the ids, add the topic to each paper's theme_groups, confirm the topic and note
     that its existing papers were tagged, commit and push, all in the bridge's own copy of the repository.

    python3 bridge/add_topic.py "Visuomotor Policies"                        # the topic exists (suggested or confirmed)
    python3 bridge/add_topic.py "Visuomotor Policies" --create "what belongs"   # make it (confirmed) first
    python3 bridge/add_topic.py "Visuomotor Policies" --ids ids.json          # apply ids you chose (no Claude)
The bridge runs it when you approve a topic in the dashboard; weekly runs run it for approved topics not yet tagged.
"""
import csv, datetime, io, json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import add_paper as ap
from add_paper import CLONE, PAPERS, GROUPS, Stop, log

TAGGED = 'Existing papers tagged'   # the marker in a topic's notes: done, never again
MAX_GROUPS = 5


def read_groups():
    with open(os.path.join(CLONE, GROUPS), newline='', encoding='utf-8') as f:
        r = csv.DictReader(f, delimiter='|')
        return r.fieldnames, list(r)


def write_csv(name, fields, rows, delim=','):
    path = os.path.join(CLONE, name)
    with open(path, 'rb') as f: nl = '\r\n' if b'\r\n' in f.read(20000) else '\n'
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, delimiter=delim, lineterminator=nl, extrasaction='ignore')
    w.writeheader()
    for r in rows: w.writerow({k: r.get(k) or '' for k in fields})
    with open(path, 'w', encoding='utf-8', newline='') as f: f.write(buf.getvalue())


def topic_row(rows, name):
    return next((g for g in rows if (g.get('group_name') or '').strip().lower() == name.strip().lower()), None)


def needs_tagging():
    """Confirmed topics whose existing papers were never tagged and that no paper has yet (for weekly runs)."""
    ap.fresh_clone()
    _, groups = read_groups()
    _, papers = ap.read_papers()
    have = {g for p in papers for g in (p.get('theme_groups') or '').split('|') if g}
    return [g['group_name'] for g in groups if g.get('status') == 'confirmed' and TAGGED not in (g.get('notes') or '') and g['group_name'] not in have]


def research(name, description, cb=None, on_proc=None, model='opus'):
    _, papers = ap.read_papers()
    tsv = 'id\ttitle\theadline\ttopics\tabstract\n' + '\n'.join('\t'.join(re.sub(r'\s+', ' ', x or '').strip() for x in (
        p['id'], p.get('title'), p.get('headline'), (p.get('theme_groups') or '').replace('|', ', '), (p.get('abstract') or '')[:400])) for p in papers if p.get('id'))
    with open(os.path.join(CLONE, 'topic_papers.tsv'), 'w', encoding='utf-8') as f: f.write(tsv)   # untracked; the next fresh copy removes it
    with open(os.path.join(ap.REPO_SRC, 'bridge', 'add_topic.md')) as f: instructions = f.read()
    no_mcp = os.path.join(ap.HOME, 'no-mcp.json')
    if not os.path.exists(no_mcp):
        with open(no_mcp, 'w') as f: json.dump({'mcpServers': {}}, f)
    args = [ap.claude_bin(), '-p', '--output-format', 'stream-json', '--verbose', '--model', model, '--append-system-prompt', instructions,
            '--tools', 'Read', 'Grep', 'Glob', '--allowedTools', 'Read(./**)', 'Grep(./**)', 'Glob(./**)',
            '--strict-mcp-config', '--mcp-config', no_mcp, '--setting-sources', '']
    env = dict(os.environ); env['PATH'] = os.path.dirname(ap.claude_bin()) + ':' + env.get('PATH', '/usr/bin:/bin')
    proc = subprocess.Popen(args, cwd=CLONE, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True)
    if on_proc: on_proc(proc)
    proc.stdin.write(f'Topic: {name}\nDescription: {description or "(none given: go by the name)"}\n\nDecide which papers in topic_papers.tsv belong in it and answer with the JSON block only.')
    proc.stdin.close()
    result = ''
    for line in proc.stdout:
        try: e = json.loads(line)
        except Exception: continue
        if e.get('type') == 'assistant': log('Reading your papers…', cb)
        elif e.get('type') == 'result': result = e.get('result') or ''
    proc.wait()
    if proc.returncode and not result: raise RuntimeError('Claude Code stopped: ' + proc.stderr.read()[-300:])
    m = re.search(r'```(?:json)?\s*(\{[\s\S]*\})\s*```', result) or re.search(r'(\{[\s\S]*\})', result)
    try: return list(dict.fromkeys(json.loads(m.group(1)).get('ids') or []))
    except Exception: raise Stop('Claude’s answer could not be read; no papers were tagged.')


def publish(name, ids, create_desc=None, cb=None):
    """Add the topic to these papers (and confirm it); retried from a fresh copy if someone pushed meanwhile."""
    today = datetime.date.today().isoformat()
    for attempt in range(3):
        log('Tagging the papers…', cb)
        ap.fresh_clone()
        gfields, groups = read_groups()
        g = topic_row(groups, name)
        if not g:
            if create_desc is None: raise Stop(f'There is no topic called “{name}”.')
            order = max([int(x.get('display_order') or 0) for x in groups if (x.get('display_order') or '').isdigit()] + [0]) + 1
            g = {'group_name': name.strip(), 'status': 'confirmed', 'description': create_desc, 'display_order': str(order), 'date_added': today, 'notes': 'Added by you.'}
            groups.append(g)
        if g.get('status') == 'rejected': raise Stop(f'“{name}” was dismissed; restore it first.')
        name = g['group_name']
        pfields, papers = ap.read_papers()
        known, tagged = {p['id']: p for p in papers}, []
        for pid in ids:
            p = known.get(pid)
            if not p: continue
            gs = [x for x in (p.get('theme_groups') or '').split('|') if x]
            if name in gs or len(gs) >= MAX_GROUPS: continue
            p['theme_groups'] = '|'.join(gs + [name]); tagged.append(pid)
        g['status'] = 'confirmed'
        g['notes'] = re.sub(r'\s*' + TAGGED + r'[^.]*\.', '', g.get('notes') or '').strip()
        total = sum(1 for p in papers if name in (p.get('theme_groups') or '').split('|'))
        g['notes'] = (g['notes'] + ' ' if g['notes'] else '') + f'{TAGGED} {today} ({total} papers).'
        write_csv(PAPERS, pfields, papers)
        write_csv(GROUPS, gfields, groups, '|')
        subprocess.run([sys.executable, os.path.join(CLONE, 'make_share_pages.py')], cwd=CLONE, capture_output=True, timeout=120)
        ap.git('add', PAPERS, GROUPS); ap.git('add', '-A', 'p')
        ap.git('commit', '-q', '-m', f'Topic "{name}": tag {len(tagged)} existing papers')
        log('Publishing…', cb)
        r = ap.git('push', *(['--dry-run'] if ap.DRY_RUN else []), f'https://x-access-token:{ap.gh_token()}@{ap.REMOTE}', 'HEAD:main', check=False)
        if r.returncode == 0: return {'topic': name, 'tagged': tagged, 'group': g}
        if attempt == 2: raise RuntimeError('push failed: ' + (r.stderr or '')[-300:].replace(ap.gh_token(), '***'))


def tag(name, create_desc=None, cb=None, on_proc=None):
    log('Reading your topics…', cb)
    ap.fresh_clone()
    _, groups = read_groups()
    g = topic_row(groups, name)
    if not g and create_desc is None: raise Stop(f'There is no topic called “{name}”.')
    desc = (g or {}).get('description') or create_desc or ''
    log('Reading your papers…', cb)
    ids = research((g or {}).get('group_name') or name, desc, cb, on_proc)
    return publish(name, ids, create_desc, cb)


if __name__ == '__main__':
    a = sys.argv[1:]
    try:
        if not a: print(__doc__); sys.exit(2)
        if a[0] == '--pending':
            print('\n'.join(needs_tagging())); sys.exit(0)
        name = a[0]
        if '--ids' in a:
            with open(a[a.index('--ids') + 1]) as f: data = json.load(f)
            out = publish(name, data.get('ids', data) if isinstance(data, dict) else data, a[a.index('--create') + 1] if '--create' in a else None, cb=print)
        else:
            out = tag(name, a[a.index('--create') + 1] if '--create' in a else None, cb=print)
    except Stop as e:
        print('Not done: ' + str(e)); sys.exit(1)
    print(f"{out['topic']}: tagged {len(out['tagged'])} papers.")
