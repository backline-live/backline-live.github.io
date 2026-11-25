#!/usr/bin/env python3
"""Offline check of the built site: every local link / asset / #anchor resolves, no template leftovers.
    python3 check.py          (exit 1 on any problem; external links are listed, not fetched)"""
import re, sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urldefrag, urlparse

ROOT = Path(__file__).resolve().parent


class P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.ids = [], set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"])
        for k in ("href", "src"):
            if a.get(k) is not None:
                self.links.append((tag, a[k]))


pages = {p: P() for p in ROOT.rglob("*.html") if not any(x in p.parts for x in ("templates", ".git"))}
for p, h in pages.items():
    h.feed(p.read_text(encoding="utf-8"))
bad, ext, n = [], set(), 0
for p, h in pages.items():
    txt = p.read_text(encoding="utf-8")
    if "%%" in txt:
        bad.append("%s: template leftover %%%%" % p.relative_to(ROOT))
    for tag, url in h.links:
        n += 1
        if not url:
            bad.append("%s: empty %s" % (p.relative_to(ROOT), tag)); continue
        u = urlparse(url)
        if u.scheme in ("http", "https"):
            ext.add(url); continue
        if u.scheme:
            continue  # mailto:
        path, frag = urldefrag(url)
        t = (p.parent / unquote(path)) if path else p
        if path.startswith("/") and p.name != "404.html":
            bad.append("%s: absolute path %s (breaks on a project site)" % (p.relative_to(ROOT), url)); continue
        if t.is_dir():
            t = t / "index.html"
        if path.startswith("/"):
            continue  # 404.html uses base_path (site.json)
        if not t.exists():
            bad.append("%s: missing target %s" % (p.relative_to(ROOT), url)); continue
        if frag and t.suffix == ".html" and frag not in pages[t.resolve() if t.resolve() in pages else t].ids:
            bad.append("%s: missing anchor %s" % (p.relative_to(ROOT), url))
css = (ROOT / "assets" / "site.css").read_text(encoding="utf-8")
for m in re.finditer(r'url\("([^"]+)"\)', css):
    if not (ROOT / "assets" / m.group(1)).exists():
        bad.append("site.css: missing %s" % m.group(1))
print("%d pages, %d local links checked, %d external:" % (len(pages), n, len(ext)))
for e in sorted(ext):
    print("  ", e)
for b in bad:
    print("BAD", b)
sys.exit(1 if bad else 0)
