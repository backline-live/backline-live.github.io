# ziptie site

Static website of ziptie (landing, guide, changelog, EULA / privacy / terms, support, thanks). Plain HTML + CSS,
no JavaScript, no build server: GitHub Pages serves this folder as it is. **No product code lives here.**
Design: the approved mock `docs/mocks/site.html` of the product repo (DESIGN §4 G5a).

## Change something
| I want to | Do |
|---|---|
| set the Buy / Free trial / customer-portal link, the support email, the video, the screenshot | edit **`site.json`** (the only config; empty link = button says "Coming soon"), then `python3 build.py`, commit, push |
| refresh guide, changelog, legal pages after the product docs changed | `python3 build.py` (reads `../ziptie_dev`; or `--source <path>`), commit, push |
| change landing / support / thanks wording | edit `templates/*.html`, `python3 build.py` |
| change look | `assets/site.css` |
| check | `python3 check.py` (every local link, asset and #anchor resolves; lists external links) |

`build.py` is Python 3 stdlib only. It rewrites the generated folders (`guide/ changelog/ eula/ privacy/ terms/ support/
thanks/`, `index.html`, `404.html`): never edit those by hand. Sources, read only: `docs/GUIDE.md`, `CHANGELOG.md`,
`docs/legal/{EULA,PRIVACY,TERMS_OF_SALE}.md` of the product repo. Author notes (DRAFT banner, `[CHECK ...]`,
`[DECIDE ...]`, drafting notes) are stripped from the legal pages; the remaining `[PLACEHOLDERS]` show with a dashed
underline until filled in the source. `legal_draft: true` shows the "being checked by a lawyer" note: set it to `false`
only with the lawyer's written OK (DESIGN §4 G4). `guide_skip` leaves guide sections out (7 = internal open points).

## Polar
- Checkout success URL of the paid and the trial product: `<site URL>/thanks/`.
- `buy_url` = checkout link of the paid product, `trial_url` = checkout link of the free (EUR 0) trial product,
  `portal_url` = customer portal (same as `portal_url` in the product's `core/license.json`).

## Credits
Font Archivo (SIL Open Font License 1.1), self-hosted in `assets/fonts/`. Colours = the product's own tokens.
