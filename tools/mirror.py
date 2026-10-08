import re, sys, os, json, time, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor
SRC, OUT = sys.argv[1], sys.argv[2]
TS = '20160205131635'
BASE = 'http://bookmarked.co.in/'
h = open(SRC, encoding='utf-8', errors='replace').read()
ctx = None
def fetch(path):
    url = f'https://web.archive.org/web/{TS}id_/{BASE}{urllib.parse.quote(path, safe="/,;=&?%:")}'
    for i in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read(), r.geturl()
        except urllib.error.HTTPError as e:
            if e.code == 404: return None, f'404'
            err = str(e)
        except Exception as e:
            err = str(e)
        time.sleep(2 ** (i + 1))
    return None, err
def norm(u, rel_base=''):
    u = u.strip().strip('"\'')
    if u.startswith('data:') or not u: return None
    if u.startswith(('http://bookmarked.co.in/', 'https://bookmarked.co.in/')):
        u = u.split('bookmarked.co.in/', 1)[1]
    elif re.match(r'^(https?:)?//', u): return None
    else:
        u = os.path.normpath(os.path.join(rel_base, u)).lstrip('./') if rel_base else u.lstrip('/')
    u = u.split('#')[0].split('?')[0]
    if not u or 'index.php' in u: return None
    return u
todo = set()
for m in re.finditer(r'(?:src|href)="([^"]+)"', h):
    p = norm(m.group(1))
    if p and re.search(r'\.(css|js|jpe?g|png|gif|svg|ico|woff2?|ttf|eot|otf)$', p, re.I): todo.add(p)
done, failed = set(), {}
while todo:
    batch = sorted(todo - done - set(failed)); todo = set()
    if not batch: break
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(fetch, batch))
    for p, (data, info) in zip(batch, res):
        if data is None:
            failed[p] = info; continue
        done.add(p)
        dst = os.path.join(OUT, p); os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, 'wb').write(data)
        if p.endswith('.css'):
            css = data.decode('utf-8', 'replace')
            for m in re.finditer(r'url\(([^)]+)\)|@import\s+["\']([^"\']+)', css):
                q = norm(m.group(1) or m.group(2), os.path.dirname(p))
                if q: todo.add(q)
    print(f'round: ok={len(done)} failed={len(failed)}', flush=True)
json.dump({'ok': sorted(done), 'failed': failed}, open(os.path.join(OUT, '..', 'mirror-report.json'), 'w'), indent=1)
