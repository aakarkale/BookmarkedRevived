"""Build the static site from the archived homepage, crawled store pages and mirrored assets.

Every page goes through the same transform: trackers and third-party scripts are removed,
same-site assets become root-relative, links to archived store pages point at their static
copies, links to anything else become inert, forms post nowhere, and the shim is injected.

usage: python3 -I build_site.py <homepage html> <crawl dir> <asset dir> <output dir>
"""
import glob, json, os, re, shutil, sys, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crawl import canonical, slug  # noqa: E402

HOME, CRAWL, ASSETS, OUT = sys.argv[1:5]

# Images that blog posts hot-linked from other sites, served from archived copies instead
# (image/vendor/external/). The one with no archived copy shows the store placeholder.
EXTERNAL_IMAGES = {
    'http://assets.entrepreneur.com/article/4-books-every-entrepreneur-should-read-1.jpg': '4-books-every-entrepreneur-should-read-1.jpg',
    'http://assets.entrepreneur.com/article/built-to-sell.jpg': 'built-to-sell.jpg',
    'http://assets.entrepreneur.com/article/choose-yourself.jpg': 'choose-yourself.jpg',
    'https://assets.entrepreneur.com/static/1424807364-sleep-info.jpg': '1424807364-sleep-info.jpg',
    'https://patilabhi95.files.wordpress.com/2015/01/22e06-bookmarked.jpg?w=400&h=160': '22e06-bookmarked.jpg',
    'http://www.gravatar.com/avatar/08432a6bb1d51d71ffcffaa44e72b497?d=&s=60': 'gravatar-08432a6bb1d51d71ffcffaa44e72b497.jpg',
    'http://www.gravatar.com/avatar/60743b9b1e53dedb3b22977fdfaaf40e?d=&s=60': 'gravatar-60743b9b1e53dedb3b22977fdfaaf40e.jpg',
    'http://assets.entrepreneur.com/article/4-books-every-entrepreneur-should-read-4.jpg': None,
}
SITE = r'https?://(?:www\.)?bookmarked\.co\.in(?::80)?/'
TRACKERS = ('GoogleAnalyticsObject', '_vengage', 'vetrack', 'addthis', 'connect.facebook.net',
            'platform.twitter.com', 'apis.google.com', 'hellobar', 'zopim', 'tawk.to')

meta = json.load(open(os.path.join(CRAWL, 'pages.json')))
pages = {k: v for k, v in meta.items() if v['status'] == 'ok'}
report = {'inert_links': {}, 'zoom_fallbacks': 0, 'missing_assets': set(), 'external_refs': set(),
          'removed_scripts': {}, 'image_substitutes': {}, 'dropped_scripts': set()}


def have(path):
    return os.path.isfile(os.path.join(ASSETS, path))


# Index of archived images by picture, ignoring OpenCart's "-<w>x<h>" cache suffix, so a missing
# size of a picture can be replaced by another archived size or by its full-size original.
IMG = re.compile(r'\.(jpe?g|png|gif)$', re.I)
PLACEHOLDERS = ['image/cache/data/No_image_available-475x524.jpg', 'image/data/No_image_available.jpg']


def picture(path):
    p = re.sub(r'^image/cache/', 'image/', path)
    return IMG.sub('', re.sub(r'-\d+x\d+(?=\.[A-Za-z]+$)', '', p)).lower()


by_picture = {}
for d, _, fs in os.walk(os.path.join(ASSETS, 'image')):
    for f in fs:
        rel = os.path.relpath(os.path.join(d, f), ASSETS)
        if IMG.search(f):
            by_picture.setdefault(picture(rel), []).append(rel)


def substitute(path):
    """Archived stand-in for an image that was never archived, or None."""
    if not IMG.search(path):
        return None
    options = by_picture.get(picture(path), [])
    if options:
        # Prefer the full-size original, then the largest cached size.
        def size(p):
            m = re.search(r'-(\d+)x(\d+)\.[A-Za-z]+$', p)
            return (not p.startswith('image/data/'), -(int(m.group(1)) * int(m.group(2)) if m else 0))
        return sorted(options, key=size)[0]
    return next((p for p in PLACEHOLDERS if have(p)), None)


def enc(path):
    return '/' + urllib.parse.quote(path, safe="/,;=-._~")


def out_slug(key):
    # One path segment per page ("product-category-path-20-page-2"). Nested paths would put a
    # page next to a directory of the same name (product/manufacturer.html beside
    # product/manufacturer/info/...), which clean URLs cannot serve unambiguously.
    return slug(key).replace('/', '-')


def page_url(key):
    s = out_slug(key)
    return '/' if s == 'index' else '/' + urllib.parse.quote(s, safe='/-_.')


def store_target(url):
    """Static URL for an archived store page, or None when there is no static copy."""
    key = canonical(url)
    return page_url(key) if key in pages else None


BLANK_GIF = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'
OPEN_SANS = '/catalog/view/theme/pav_pharmacy/stylesheet/open-sans.css'


def transform(html):
    # Normalise single-quoted attributes so every rule below sees one quoting style.
    html = re.sub(r"""(\s(?:href|src|action|value|data-[a-z-]+))='([^'"]*)'""", r'\1="\2"', html)
    html = re.sub(r'<base href="[^"]*"\s*/?>\n?', '', html)

    # Quick View pages link Google's Open Sans stylesheet; an archived copy is served locally.
    html = re.sub(r'href="http://fonts\.googleapis\.com/css\?family=Open\+Sans:[^"]*"', f'href="{OPEN_SANS}"', html)

    # The contact page map needs the Google Maps API, which is not loaded: drop its plugin and setup.
    html = re.sub(r'<script[^>]*\ssrc="[^"]*/gmap/gmap3[^"]*"[^>]*>\s*</script>\n?', '', html)
    html = re.sub(r'<script(?![^>]*\ssrc=)[^>]*>(?:(?!</script>).)*?\.gmap3\(.*?</script>', '', html, flags=re.S)

    # Listings hid their pagination and loaded further pages by AJAX on scroll (infinitescroll).
    # Without a backend that would strand visitors on page 1, so the setup is removed and the
    # theme's pagination bar (already in the markup) links to the static pages instead.
    html = re.sub(r'<script(?![^>]*\ssrc=)[^>]*>(?:(?!</script>).)*?\.infinitescroll\(.*?</script>', '', html, flags=re.S)

    # Third-party scripts: external <script src> and inline scripts that load or call trackers.
    def drop_external(m):
        report['removed_scripts'][m.group(1)] = report['removed_scripts'].get(m.group(1), 0) + 1
        return ''
    html = re.sub(r'<script[^>]*\ssrc="((?:https?:)?//(?!(?:www\.)?bookmarked\.co\.in)[^"]*)"[^>]*>\s*</script>',
                  drop_external, html)

    def drop_inline(m):
        body = m.group(0)
        hit = next((t for t in TRACKERS if t in body), None)
        if hit or 'formNewLestter' in body:
            label = hit or 'newsletter-ajax'
            report['removed_scripts'][label] = report['removed_scripts'].get(label, 0) + 1
            return ''
        return body
    html = re.sub(r'<script(?![^>]*\ssrc=)[^>]*>.*?</script>', drop_inline, html, flags=re.S)

    # Zoom links to full-size originals that were never archived fall back to the thumbnail.
    def fix_zoom(m):
        path = urllib.parse.unquote(re.sub(SITE, '', m.group(2)).replace('&amp;', '&'))
        if have(path):
            return m.group(0)
        thumbs = re.findall(r'itemprop="image" src="([^"]+)"', html[:m.start()])
        if not thumbs:
            return m.group(0)
        report['zoom_fallbacks'] += 1
        return m.group(1) + thumbs[-1] + m.group(3)
    html = re.sub(r'(<a href=")(' + SITE + r'image/data/[^"]+)(" class="info-view colorbox)', fix_zoom, html)

    # Store URLs in any attribute (href, option value, data-*): archived page or inert.
    def store(m):
        attr, url = m.group(1), m.group(2)
        target = store_target(url)
        if target:
            return f'{attr}="{target}"'
        key = re.sub(r'&(amp;)?', '&', url.split('?', 1)[-1])
        report['inert_links'][key] = report['inert_links'].get(key, 0) + 1
        if attr == 'src':
            return f'src="{BLANK_GIF}"'  # server-generated images (captcha): nothing to show
        return f'{attr}="#" data-store-link' if attr == 'href' else f'{attr}="#"'
    html = re.sub(r'(href|src|value|data-[a-z-]+)="((?:' + SITE + r')?index\.php\?[^"]*|' + SITE[:-1] + r'/?)"', store, html)

    # Same-site assets become root-relative and percent-encoded.
    def localize(m):
        path = urllib.parse.unquote(m.group(2).replace('&amp;', '&'))
        if not have(path):
            stand_in = substitute(path)
            if stand_in:
                report['image_substitutes'][path] = stand_in
                path = stand_in
            else:
                report['missing_assets'].add(path)
        return m.group(1) + enc(path)
    html = re.sub(r'((?:src|href|data-[a-z-]+)=")' + SITE + r'([^"#?]+)', localize, html)
    html = re.sub(r'((?:src|href|data-[a-z-]+)=")((?:catalog|image)/[^"]+)', localize, html)
    html = re.sub(r'(url\()' + SITE + r'([^)]+)', localize, html)

    # Hot-linked rupee symbol from Wikimedia: archived copies are served locally.
    html = re.sub(r'src="(?:https?:)?//upload\.wikimedia\.org/[^"]*?/7px-Indian_Rupee_symbol\.svg\.png"',
                  'src="/image/vendor/7px-Indian_Rupee_symbol.svg.png"', html)
    html = re.sub(r'srcset="//upload\.wikimedia\.org/[^"]*"',
                  'srcset="/image/vendor/11px-Indian_Rupee_symbol.svg.png 1.5x"', html)

    def vendored(m):
        url = m.group(1).replace('&amp;', '&')
        if url not in EXTERNAL_IMAGES:
            return m.group(0)
        name = EXTERNAL_IMAGES[url]
        return f'src="/image/vendor/external/{name}"' if name else f'src="{enc(PLACEHOLDERS[0])}"'
    html = re.sub(r'src="(https?://[^"]+)"', vendored, html)

    # Theme scripts that were never archived and are never called (jquery.parallax): drop the tag.
    def missing_script(m):
        path = urllib.parse.unquote(m.group(1)).lstrip('/')
        if have(path):
            return m.group(0)
        report['dropped_scripts'].add(path)
        return ''
    html = re.sub(r'<script[^>]*\ssrc="(/[^"]+\.js)"[^>]*>\s*</script>\n?', missing_script, html)

    # Forms keep their markup but post nowhere; the shim shows a notice on submit.
    html = re.sub(r'(<form\b[^>]*?)\s(?:action|method)="[^"]*"', r'\1', html)
    html = re.sub(r'(<form\b[^>]*?)\s(?:action|method)="[^"]*"', r'\1', html)

    # Outbound links must not hand window.opener / referrer to third parties.
    def outbound(m):
        tag = m.group(0)
        return tag if ' rel=' in tag else tag[:-1] + ' rel="noopener noreferrer">'
    html = re.sub(r'<a\s[^>]*href="https?://(?!(?:www\.)?bookmarked\.co\.in)[^"]*"[^>]*>', outbound, html)

    # The shim goes right after jQuery so it is in place before any inline script makes a request.
    html, n = re.subn(r'(<script[^>]*\ssrc="/catalog/view/javascript/jquery/jquery-1\.7\.1\.min\.js"[^>]*>\s*</script>)',
                      r'\1\n<script type="text/javascript" src="/static-shim.js"></script>', html, count=1)
    assert n == 1, 'page without jQuery'

    # Resources (not links) still pointing off-site would be blocked by the CSP: report them.
    report['external_refs'] |= set(re.findall(r'\ssrc="((?:https?:)?//[^"]+)"', html))
    report['external_refs'] |= set(re.findall(r'<link\b[^>]*\shref="((?:https?:)?//[^"]+)"', html))
    return html


if os.path.exists(OUT):
    shutil.rmtree(OUT)
shutil.copytree(ASSETS, OUT)

for key, info in sorted(pages.items()):
    src = HOME if key == 'common/home' else os.path.join(CRAWL, 'pages', info['file'])
    dst = os.path.join(OUT, out_slug(key) + '.html')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, 'w', encoding='utf-8').write(transform(open(src, encoding='utf-8').read()))

# Google web fonts were hot-linked over http://; they are served from fonts/vendor/ instead.
font_css = os.path.join(OUT, 'catalog/view/theme/pav_pharmacy/stylesheet/font.css')
css = open(font_css, encoding='utf-8').read()
css = re.sub(r'url\(https?://(?:fonts\.gstatic\.com|themes\.googleusercontent\.com)/[^)]*/([^/)]+)\)',
             r'url(../fonts/vendor/\1)', css)
open(font_css, 'w', encoding='utf-8').write(css)
for f in re.findall(r'url\(\.\./fonts/vendor/([^)]+)\)', css):
    assert os.path.isfile(os.path.join(OUT, 'catalog/view/theme/pav_pharmacy/fonts/vendor', f)), f
css_ext = [(os.path.relpath(f, OUT), u) for f in glob.glob(os.path.join(OUT, '**/*.css'), recursive=True)
           for u in re.findall(r'url\(\s*[\'"]?((?:https?:)?//[^)\'"]+)', open(f, encoding='utf-8', errors='replace').read())]

shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static-shim.js'), OUT)

# Every page must be addressable without ambiguity: no "x.html" next to a directory "x/".
clashes = [os.path.relpath(f, OUT) for f in glob.glob(os.path.join(OUT, '**/*.html'), recursive=True)
           if os.path.isdir(f[:-5])]
assert not clashes, clashes

print(f'pages written: {len(pages)}')
print(f'zoom fallbacks: {report["zoom_fallbacks"]}')
subs = report['image_substitutes']
print(f'images never archived: {len(subs)} replaced '
      f'({sum(1 for v in subs.values() if "No_image_available" in v)} by the store placeholder, the rest by another archived size)')
print('removed scripts:', json.dumps(report['removed_scripts'], indent=1, sort_keys=True))
print('dropped never-archived scripts:', sorted(report['dropped_scripts']))
print(f'distinct inert store links: {len(report["inert_links"])}')
print('missing assets:', len(report['missing_assets']), *sorted(report['missing_assets'])[:40], sep='\n  ')
print('external resources left:', *sorted(report['external_refs']), sep='\n  ')
print('external urls in CSS:', *css_ext, sep='\n  ')
json.dump({'image_substitutes': report['image_substitutes'], 'inert_links': report['inert_links'], 'missing_assets': sorted(report['missing_assets']),
           'external_refs': sorted(report['external_refs'])},
          open(os.path.join(CRAWL, 'build-report.json'), 'w'), indent=1, sort_keys=True)
