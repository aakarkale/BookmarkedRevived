import json, sys, os, time, urllib.request, urllib.parse
REP, OUT = sys.argv[1], sys.argv[2]
rep = json.load(open(REP))
def get(url):
    for i in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r: return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
        except Exception: pass
        time.sleep(2 ** (i + 1))
still = {}
for p in list(rep['failed']):
    q = urllib.parse.quote(p, safe='/,;=')
    data = get(f'https://web.archive.org/web/20160205131635id_/http://bookmarked.co.in/{q}')
    if data is None:
        cdx = get(f'https://web.archive.org/cdx/search/cdx?url=bookmarked.co.in/{urllib.parse.quote(q, safe="/")}&output=json&filter=statuscode:200&limit=5')
        rows = json.loads(cdx or b'[]')[1:]
        for row in rows:
            data = get(f'https://web.archive.org/web/{row[1]}id_/{row[2]}')
            if data: break
    if data:
        dst = os.path.join(OUT, p); os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, 'wb').write(data); rep['ok'].append(p); print('OK ', p)
    else:
        still[p] = 'unavailable'; print('MISS', p)
rep['failed'] = still
json.dump(rep, open(REP, 'w'), indent=1)
