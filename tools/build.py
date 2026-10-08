"""Turn the raw Wayback capture of bookmarked.co.in into a self-contained static page.

usage: python3 -I build.py <raw home.html> <mirrored asset dir> <output public dir>
"""
import os, re, shutil, sys, urllib.parse

SRC, ASSETS, OUT = sys.argv[1:4]
html = open(SRC, encoding='utf-8').read()
log = []

def have(path):
    return os.path.isfile(os.path.join(ASSETS, urllib.parse.unquote(path)))

def enc(path):
    return '/' + urllib.parse.quote(path, safe="/,;=-._~")

# 1. No <base>: every URL below becomes root-relative.
html, n = re.subn(r'<base href="[^"]*"\s*/>\n?', '', html); log.append(f'removed base: {n}')

# 2. Third-party trackers (Google Analytics, VWO engage, Hello Bar) and the AJAX newsletter handler.
def drop_script(pattern, label):
    global html
    html, n = re.subn(r'<script(?![^>]*\bsrc=)[^>]*>(?:(?!</script>).)*?' + pattern + r'.*?</script>', '', html, flags=re.S)
    log.append(f'removed inline script {label}: {n}')
drop_script(r'GoogleAnalyticsObject', 'google-analytics')
drop_script(r'_vengage', 'vwo-engage')
drop_script(r'formNewLestter', 'newsletter-ajax')
html, n = re.subn(r'<script src="//my\.hellobar\.com/[^"]*"[^>]*></script>', '', html); log.append(f'removed hellobar: {n}')

# 3. Zoom links point at full-size originals; a few were never archived, so fall back to the
#    product's own thumbnail (the nearest preceding itemprop="image").
def fix_zoom(m):
    href = m.group(2)
    path = href.split('bookmarked.co.in/', 1)[1]
    if have(path):
        return m.group(0)
    thumb = re.findall(r'itemprop="image" src="([^"]+)"', html[:m.start()])[-1]
    log.append(f'zoom fallback: {path}')
    return m.group(1) + thumb + m.group(3)
html = re.sub(r'(<a href=")(https?://bookmarked\.co\.in/image/data/[^"]+)(" class="info-view colorbox)', fix_zoom, html)

# 4. Store routes (index.php?route=...) have no backend any more: make them inert.
html, n = re.subn(r'href="https?://bookmarked\.co\.in/index\.php\?route=common/home"', 'href="/"', html); log.append(f'home route links: {n}')
html, n = re.subn(r'href="https?://bookmarked\.co\.in/index\.php[^"]*"', 'href="#" data-store-link', html); log.append(f'store links made inert: {n}')
html, n = re.subn(r'href="https?://bookmarked\.co\.in/"', 'href="/"', html); log.append(f'home links: {n}')

# 5. Same-site assets become root-relative and percent-encoded (paths contain spaces and commas).
missing = set()
def localize(m):
    path = urllib.parse.unquote(m.group(2).replace('&amp;', '&'))
    if not have(path):
        missing.add(path)
    return m.group(1) + enc(path)
html = re.sub(r'((?:src|href|data-thumb)=")https?://bookmarked\.co\.in/([^"#?]+)', localize, html)
html = re.sub(r'((?:src|href)=")(catalog/[^"]+)', localize, html)

# 6. Rupee symbol was hot-linked from Wikimedia; serve the archived copies ourselves.
html = re.sub(r'src="(?:https?:)?//upload\.wikimedia\.org/[^"]*?/7px-Indian_Rupee_symbol\.svg\.png"',
              'src="/image/vendor/7px-Indian_Rupee_symbol.svg.png"', html)
html = re.sub(r'srcset="//upload\.wikimedia\.org/[^"]*"',
              'srcset="/image/vendor/11px-Indian_Rupee_symbol.svg.png 1.5x"', html)

# 7. Newsletter form keeps its markup but posts nowhere.
html, n = re.subn(r'<form id="formNewLestter" method="post" action="[^"]*"', '<form id="formNewLestter"', html)
log.append(f'newsletter form neutralised: {n}')

# 8. Outbound links must not hand window.opener / referrer to third parties.
def outbound(m):
    tag = m.group(0)
    return tag if ' rel=' in tag else tag[:-1] + ' rel="noopener noreferrer">'
html = re.sub(r'<a\s[^>]*href="https?://(?!bookmarked\.co\.in)[^"]*"[^>]*>', outbound, html)

# 9. Shim that stubs the cart/search/newsletter JS. Loaded last so it overrides the theme.
html, n = re.subn(r'</body>', '<script type="text/javascript" src="/static-shim.js"></script>\n</body>', html, count=1)
assert n == 1

leftovers = sorted(set(re.findall(r'https?://bookmarked\.co\.in[^"\s<]*', html)))
ext = sorted(set(re.findall(r'(?:src|href)="((?:https?:)?//[^"]+)"', html)))

# Copy assets and patch CSS that points at external hosts.
if os.path.exists(OUT):
    shutil.rmtree(OUT)
shutil.copytree(ASSETS, OUT)
font_css = os.path.join(OUT, 'catalog/view/theme/pav_pharmacy/stylesheet/font.css')
css = open(font_css, encoding='utf-8').read()
# Google web fonts were hot-linked over http://; they are served from fonts/vendor/ instead.
css, n = re.subn(r'url\(https?://(?:fonts\.gstatic\.com|themes\.googleusercontent\.com)/[^)]*/([^/)]+)\)', r'url(../fonts/vendor/\1)', css)
open(font_css, 'w', encoding='utf-8').write(css); log.append(f'web font urls localised: {n}')
for f in re.findall(r'url\(\.\./fonts/vendor/([^)]+)\)', css):
    assert os.path.isfile(os.path.join(OUT, 'catalog/view/theme/pav_pharmacy/fonts/vendor', f)), f
css_ext = [(f, u) for f in __import__('glob').glob(os.path.join(OUT, '**/*.css'), recursive=True)
           for u in re.findall(r'url\(\s*[\'"]?((?:https?:)?//[^)\'"]+)', open(f, encoding='utf-8', errors='replace').read())]
print('external urls left in CSS:', *css_ext, sep='\n  ')
open(os.path.join(OUT, 'index.html'), 'w', encoding='utf-8').write(html)
shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static-shim.js'), OUT)

print('\n'.join(log))
print('missing assets referenced by page:', *sorted(missing), sep='\n  ')
print('remaining bookmarked.co.in URLs (non-link text):', *leftovers, sep='\n  ')
print('external src/href:', *ext, sep='\n  ')
