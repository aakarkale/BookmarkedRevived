"""Crawl the archived bookmarked.co.in store pages reachable from the homepage.

Every store link is reduced to a canonical key (route plus the parameters that identify a
page). A key is fetched only when the Wayback CDX index has a capture of it; the capture
nearest to the homepage snapshot is used, and captures outside 2015-01..2017-06 or not built
with the 2016 theme are rejected. Results are written to <out>/pages/<slug>.html plus
<out>/pages.json; re-running resumes and skips pages already fetched.

The CDX listing must hold every capture (not collapsed) as "<timestamp> <url>" lines, so
the nearest capture can be requested directly instead of through a redirect.

usage: python3 -I crawl.py <homepage html> <cdx listing> <out dir>
"""
import json, os, re, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

TS = '20160205131635'
TS_MIN, TS_MAX = '20150101000000', '20170630235959'

# Routes that are AJAX endpoints, server actions or search: never static pages.
SKIP_ROUTES = re.compile(r'^(module/|product/search|product/compare|checkout/cart/add|account/logout|'
                         r'common/currency|common/language|tool/|payment/|feed/|pavblog/blogs$)')
# Parameters that only re-sort or re-slice an existing page; variants are not kept.
DROP_PARAMS = {'sort', 'order', 'limit', 'filter', 'filter_name', 'filter_tag'}
PRODUCT_ROUTES = {'product/product', 'themecontrol/product'}


def canonical(url):
    """Return the canonical key for a store URL, or None when it is not a static page."""
    url = url.replace('&amp;', '&').strip()
    m = re.match(r'^(?:https?://(?:www\.)?bookmarked\.co\.in(?::80)?/)?index\.php\?(.*)$', url)
    if not m:
        if re.match(r'^https?://(?:www\.)?bookmarked\.co\.in(?::80)?/?$', url):
            return 'common/home'
        return None
    q = urllib.parse.parse_qs(m.group(1).split('#')[0], keep_blank_values=True)
    route = q.pop('route', ['common/home'])[0]
    if SKIP_ROUTES.match(route) or route.startswith('admin'):
        return None
    if route in PRODUCT_ROUTES:
        params = {'product_id': q['product_id'][0]} if 'product_id' in q else None
        if params is None:
            return None
    else:
        params = {k: v[0] for k, v in q.items() if k not in DROP_PARAMS and v[0] != ''}
        if params.get('page') == '1':
            del params['page']
    if route == 'common/home':
        return 'common/home'
    return route + ''.join(f'/{k}-{params[k]}' for k in sorted(params, key=lambda k: (k == 'page', k)))


def slug(key):
    return 'index' if key == 'common/home' else re.sub(r'[^A-Za-z0-9/_.-]', '_', key)


def get(url):
    for i in range(8):
        try:
            # Successful responses arrive within ~4 s; the egress proxy cuts stalled tunnels at
            # ~11 s, so a short timeout abandons doomed attempts early.
            with urllib.request.urlopen(url, timeout=9) as r:
                return r.read(), r.geturl()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, None
        except Exception:
            pass
        time.sleep(2)  # the egress proxy drops ~1 in 3 archive connections; retry promptly
    raise RuntimeError('network: ' + url)


LINK = re.compile(r'href="((?:https?://(?:www\.)?bookmarked\.co\.in(?::80)?/)?index\.php\?[^"]*|https?://(?:www\.)?bookmarked\.co\.in/?)"')


def main():
    home, cdx_path, out = sys.argv[1:4]
    os.makedirs(os.path.join(out, 'pages'), exist_ok=True)
    meta_path = os.path.join(out, 'pages.json')
    meta = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
    captured = {}
    for line in open(cdx_path):
        ts, orig = line.split(' ', 1)
        k = canonical(orig.strip())
        if k and TS_MIN <= ts <= TS_MAX:
            captured.setdefault(k, []).append((ts, orig.strip()))
    for caps in captured.values():  # nearest to the homepage snapshot first
        caps.sort(key=lambda c: abs(int(c[0]) - int(TS)))

    def links_of(html):
        return {k for k in (canonical(u) for u in LINK.findall(html)) if k}

    def fetch(key):
        if key in meta and meta[key].get('status') in ('ok', 'rejected', 'missing'):
            return key, meta[key]
        for cap_ts, orig in captured.get(key, [])[:3]:
            target = re.sub(r'^https?://(?:www\.)?bookmarked\.co\.in(?::80)?', 'http://bookmarked.co.in', orig)
            try:
                data, final = get(f'https://web.archive.org/web/{cap_ts}id_/' + urllib.parse.quote(orig, safe=':/?&=%,;'))
            except RuntimeError:
                return key, {'status': 'error'}  # transient; retried on the next run
            if data is None:
                continue
            ts = re.search(r'/web/(\d{14})', final).group(1)
            html = data.decode('utf-8', 'replace')
            if not (TS_MIN <= ts <= TS_MAX) or 'pav_pharmacy' not in html:
                continue
            path = os.path.join(out, 'pages', slug(key) + '.html')
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, 'w', encoding='utf-8').write(html)
            return key, {'status': 'ok', 'timestamp': ts, 'source': target, 'file': slug(key) + '.html'}
        return key, {'status': 'rejected' if captured.get(key) else 'missing'}

    home_html = open(home, encoding='utf-8').read()
    frontier = links_of(home_html) - {'common/home'}
    meta['common/home'] = {'status': 'ok', 'timestamp': TS, 'source': 'http://bookmarked.co.in/', 'file': 'index.html'}
    seen = {'common/home'}
    with ThreadPoolExecutor(4) as ex:
        while frontier:
            batch = sorted(frontier - seen)
            seen |= set(batch)
            frontier = set()
            for fut in as_completed([ex.submit(fetch, k) for k in batch]):
                key, info = fut.result()
                meta[key] = info
                json.dump(meta, open(meta_path, 'w'), indent=1, sort_keys=True)
                if info['status'] == 'ok':
                    html = open(os.path.join(out, 'pages', info['file']), encoding='utf-8').read()
                    frontier |= links_of(html) - seen
            json.dump(meta, open(meta_path, 'w'), indent=1, sort_keys=True)
            ok = sum(1 for v in meta.values() if v['status'] == 'ok')
            print(f'round done: batch={len(batch)} ok={ok} total_keys={len(meta)} next={len(frontier)}', flush=True)
    print('finished', flush=True)


if __name__ == '__main__':
    main()
