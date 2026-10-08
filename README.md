# Bookmarked Revived

A static restoration of the bookmarked.co.in homepage as captured by the Wayback Machine on
5 Feb 2016 ([snapshot](https://web.archive.org/web/20160205131635/http://bookmarked.co.in/)).
The markup, CSS, JavaScript, fonts and images are the originals from that capture, served
from this repository. Nothing is loaded from third parties.

## Layout

| Path | What it is |
| --- | --- |
| `public/` | The deployable site. Vercel serves this directory as-is (see `vercel.json`). |
| `source/bookmarked.co.in-20160205131635.html` | The untouched homepage HTML from the archive (`id_` raw capture). |
| `tools/mirror.py`, `tools/retry.py` | Download every asset the page and its CSS reference from the same capture, falling back to other capture dates via the CDX index. |
| `tools/build.py` | Turns the raw HTML plus mirrored assets into `public/`. |
| `tools/static-shim.js` | Replaces the store's AJAX calls with a notice (copied to `public/`). |

## What changed from the 2016 page, and why

The original was an OpenCart 1.5 store (theme "pav_pharmacy") with a PHP backend that no longer
exists. Everything visual is unchanged; only behaviour that depended on the backend or on third
parties was altered:

- **Store actions are inert.** Add to Cart, Wish List, Compare, Quick View, search, the
  newsletter form and links to store pages (account, categories, products) show the notice
  "Bookmarked is being revived. Online ordering is not available yet." This text is new, not
  from the original. No form posts anywhere and no data is collected.
- **Trackers removed:** Google Analytics (`UA-58700825-1`), VWO Engage and Hello Bar.
- **Hot-linked assets vendored:** Raleway and Open Sans (Google Fonts, archived copies), the
  rupee symbol (Wikimedia, archived copy) and Font Awesome 4.0.3 fonts (from the npm package;
  its `.eot` is byte-identical to the archived one).
- **Zoom images:** 11 full-size product images were never archived; their zoom shows the
  archived thumbnail instead.
- **Outbound links** get `rel="noopener noreferrer"`.

`pavmegamenu/style.css` and `pavproducttabs.css` are empty files. That is faithful: the
archive's content digest for both is the SHA-1 of zero bytes.

## Security

`vercel.json` sets a Content-Security-Policy that only allows same-origin resources, blocks all
network requests from scripts (`connect-src 'none'`), all form submissions (`form-action 'none'`)
and framing, plus HSTS, `nosniff`, a referrer policy and a permissions policy.
`'unsafe-inline'` is required for scripts because the theme initialises its slider and
carousels with inline scripts placed next to their markup.

The page runs the original 2016 libraries, including jQuery 1.7.1, which has published XSS
CVEs. They are only exploitable when untrusted input reaches jQuery; this page has no user
input that reaches the DOM, no URL parameters are read, and all AJAX is aborted. Upgrade or
replace these libraries before adding any dynamic feature.

## Rebuilding

```sh
python3 -I tools/mirror.py source/bookmarked.co.in-20160205131635.html work/assets
python3 -I tools/retry.py work/mirror-report.json work/assets
# fonts/vendor, Font Awesome woff/ttf/svg and image/vendor were added by hand; see above
python3 -I tools/build.py source/bookmarked.co.in-20160205131635.html work/assets public
```

To preview locally: `python3 -m http.server -d public`.
