"""Verify that every internal link and asset in the built site resolves to a file.

Root-relative URLs are resolved the way Vercel serves `public/` with `cleanUrls`: `/a/b`
is served by `a/b.html` (or `a/b/index.html`), and `/` by `index.html`. Also lists any
resource that still points off-site. Exits non-zero when something is broken.

usage: python3 -I check_links.py <public dir>
"""
import collections, os, re, sys, urllib.parse

ROOT = sys.argv[1]


def resolves(url):
    path = urllib.parse.unquote(url.split('#')[0].split('?')[0]).lstrip('/')
    full = os.path.join(ROOT, path)
    if path == '':
        return os.path.isfile(os.path.join(ROOT, 'index.html'))
    return os.path.isfile(full) or os.path.isfile(full + '.html') or os.path.isfile(os.path.join(full, 'index.html'))


broken = collections.defaultdict(set)
external = collections.defaultdict(set)
pages = links = 0
for dirpath, _, files in os.walk(ROOT):
    for f in files:
        if not f.endswith('.html'):
            continue
        pages += 1
        page = os.path.relpath(os.path.join(dirpath, f), ROOT)
        html = open(os.path.join(dirpath, f), encoding='utf-8', errors='replace').read()
        for attr, url in re.findall(r'\s(href|src|data-[a-z-]+|value)="(/[^"/][^"]*|/)"', html):
            links += 1
            if not resolves(url):
                broken[url].add(page)
        for url in re.findall(r'\ssrc="((?:https?:)?//[^"]+)"', html) + \
                re.findall(r'<link\b[^>]*\shref="((?:https?:)?//[^"]+)"', html):
            external[url].add(page)

print(f'pages: {pages}, internal references checked: {links}')
print(f'broken internal references: {len(broken)}')
for url, where in sorted(broken.items())[:50]:
    print(f'  {url}  (in {len(where)} pages, e.g. {sorted(where)[0]})')
print(f'off-site resources: {len(external)}')
for url, where in sorted(external.items())[:50]:
    print(f'  {url}  (in {len(where)} pages)')
sys.exit(1 if broken or external else 0)
