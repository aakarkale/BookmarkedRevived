"""Download every same-site asset referenced by archived pages (and by the CSS they load).

Files already present in the asset directory are skipped, so this can be re-run as new pages
are crawled. Each asset is requested at the homepage timestamp; the Wayback Machine redirects
to the nearest capture of any date. A JSON report of failures is written next to the assets.

With --cdx <listing> (repeatable; "<timestamp> <url>" lines from a CDX prefix query collapsed
by urlkey), assets under a listed prefix are fetched at their exact capture timestamp in one
request, and assets the listing does not contain are reported as not archived without a request.

usage: python3 -I mirror.py [--cdx <listing>]... <asset dir> <page.html> [<page.html> ...]
"""
import json, os, re, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

TS = '20160205131635'
ASSET_EXT = re.compile(r'\.(css|js|jpe?g|png|gif|svg|ico|woff2?|ttf|eot|otf)$', re.I)
SITE = re.compile(r'^https?://(?:www\.)?bookmarked\.co\.in(?::80)?/')


def norm(url, rel_base=''):
    """Map a reference to a site-relative path, or None for external/data/store URLs."""
    url = url.strip().strip('"\'').replace('&amp;', '&')
    if not url or url.startswith(('data:', '#', 'javascript:', 'mailto:')):
        return None
    if SITE.match(url):
        url = SITE.sub('', url)
    elif re.match(r'^(https?:)?//', url):
        return None
    elif rel_base:
        url = os.path.normpath(os.path.join(rel_base, url))
    url = urllib.parse.unquote(url.split('#')[0].split('?')[0]).lstrip('/')
    if not url or 'index.php' in url or url.startswith('..') or not ASSET_EXT.search(url):
        return None
    return url


def html_assets(html):
    refs = re.findall(r'\s(?:src|href|data-[a-z-]+|rel)="([^"]+)"', html)
    refs += re.findall(r'url\(([^)]+)\)', html)
    return {p for p in map(norm, refs) if p}


def css_assets(css, css_path):
    refs = re.findall(r'url\(([^)]+)\)|@import\s+["\']([^"\']+)', css)
    return {p for p in (norm(a or b, os.path.dirname(css_path)) for a, b in refs) if p}


CAPTURES, PREFIXES = {}, set()


def fetch(path):
    if path.lower() in CAPTURES:
        ts, orig = CAPTURES[path.lower()]
        url = f'https://web.archive.org/web/{ts}id_/' + urllib.parse.quote(orig, safe=':/?&=%,;')
    elif path.split('/', 1)[0] in PREFIXES:
        return None, 'not archived'
    else:
        url = f'https://web.archive.org/web/{TS}id_/http://bookmarked.co.in/' + urllib.parse.quote(path, safe='/,;=')
    for i in range(8):
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                return r.read(), None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, 'not archived'
            err = f'http {e.code}'
        except Exception as e:
            err = str(e)
        time.sleep(2)  # the egress proxy drops ~1 in 3 archive connections; retry promptly
    return None, err


def main():
    args = sys.argv[1:]
    while args[0] == '--cdx':
        for line in open(args[1]):
            ts, orig = line.split(' ', 1)
            path = urllib.parse.unquote(SITE.sub('', orig.strip()).split('?')[0])
            CAPTURES.setdefault(path.lower(), (ts, orig.strip()))
            PREFIXES.add(path.split('/', 1)[0])
        args = args[2:]
    out, pages = args[0], args[1:]
    todo = set()
    for p in pages:
        todo |= html_assets(open(p, encoding='utf-8', errors='replace').read())
    # CSS already on disk may reference assets that are not on disk yet.
    for root, _, files in os.walk(out):
        for f in files:
            if f.endswith('.css'):
                path = os.path.relpath(os.path.join(root, f), out)
                todo |= css_assets(open(os.path.join(root, f), encoding='utf-8', errors='replace').read(), path)
    failed, fetched = {}, 0
    while True:
        batch = sorted(p for p in todo if p not in failed and not os.path.exists(os.path.join(out, p)))
        if not batch:
            break
        todo = set()
        with ThreadPoolExecutor(4) as ex:
            for p, (data, err) in zip(batch, ex.map(fetch, batch)):
                if data is None:
                    failed[p] = err
                    continue
                dst = os.path.join(out, p)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                open(dst, 'wb').write(data)
                fetched += 1
                if p.endswith('.css'):
                    todo |= css_assets(data.decode('utf-8', 'replace'), p)
        print(f'fetched={fetched} failed={len(failed)}', flush=True)
    report = os.path.join(os.path.dirname(os.path.abspath(out)), 'mirror-report.json')
    json.dump({'failed': failed}, open(report, 'w'), indent=1, sort_keys=True)
    print('done; failures in', report)


if __name__ == '__main__':
    main()
