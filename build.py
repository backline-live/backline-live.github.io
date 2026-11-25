#!/usr/bin/env python3
"""Backline site generator. Plain Python 3, standard library only.

    python3 build.py                       # docs from ../av_infrastructure, store links from site.json
    python3 build.py --source /path/to/av_infrastructure

Writes the whole site (index.html, guide/, changelog/, eula/, privacy/, terms/, support/, thanks/, 404.html,
sitemap.xml) next to this file. The generated HTML is committed: GitHub Pages serves the repo root as it is.
Sources read from the product repo (never written there): docs/GUIDE.md, CHANGELOG.md, docs/legal/{EULA,PRIVACY,
TERMS_OF_SALE}.md. Store links and texts that change: site.json.
"""
import argparse, html, json, re, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEGAL = [  # key, source file, page title, nav label
    ("eula", "EULA.md", "End-user licence agreement", "EULA"),
    ("privacy", "PRIVACY.md", "Privacy policy", "Privacy"),
    ("terms", "TERMS_OF_SALE.md", "Terms of sale", "Terms of sale"),
]
LEGAL_REF = {"EULA.md": "eula", "PRIVACY.md": "privacy", "TERMS_OF_SALE.md": "terms"}
MARK = ('<svg viewBox="0 0 22 22" fill="none" aria-hidden="true"><rect x="1" y="4" width="9" height="14" rx="1.5" '
        'stroke="#ff453a" stroke-width="1.6"/><rect x="12" y="4" width="9" height="14" rx="1.5" stroke="#32d74b" '
        'stroke-width="1.6"/></svg>')
esc = html.escape


def img_size(path):
    """(width, height) of a PNG or JPEG (stdlib only); (1920, 1080) if unknown."""
    try:
        b = Path(path).read_bytes()
        if b[:8] == b"\x89PNG\r\n\x1a\n":
            return int.from_bytes(b[16:20], "big"), int.from_bytes(b[20:24], "big")
        i = 2
        while b[:2] == b"\xff\xd8" and i < len(b) - 9:
            if b[i] != 0xFF:
                i += 1
                continue
            m = b[i + 1]
            if m in (0xC0, 0xC1, 0xC2):
                return int.from_bytes(b[i + 7:i + 9], "big"), int.from_bytes(b[i + 5:i + 7], "big")
            i += 2 + int.from_bytes(b[i + 2:i + 4], "big")
    except OSError:
        pass
    return 1920, 1080
GUIDE_PATCH = [(
    "1. Get the system: `git clone` the repo into any folder you like (for example `~/Documents/av_infrastructure`).",
    "1. Get the files: after the purchase (or the free trial), open the order email and press **Access purchase**: this is your "
    "Polar customer portal. There press **Connect GitHub** (your own GitHub account): GitHub invites you to the private release "
    "repository. Accept the invitation (GitHub email, or github.com/notifications), then download `Backline-<version>.zip` from the "
    "repository's Releases and unzip it, or `git clone` the repository, into any "
    "folder you like (for example `~/Documents/backline`). Your licence key is shown in the same portal and in the order email "
    "(the free trial gets a key too, valid 14 days).")]


# ------------------------------------------------------------------ markdown (the subset the docs use)
def slugify(s):
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s).lower().replace("'", "").replace("\u2019", "")
    s = re.sub(r"^\d+[.)]?\s+", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "section"


class Md:
    """Tiny markdown -> HTML. `ctx` decides how links and ids are resolved."""

    def __init__(self, link_md=None, section_ref=None, h_offset=0):
        self.link_md = link_md or (lambda name: None)      # 'GUIDE.md' -> url or None
        self.section_ref = section_ref                       # '§3' -> url or None
        self.h_offset = h_offset
        self.heads = []                                      # (level, id, text)
        self.ids = set()
        self.anchors = []                                    # (text_anchor, ...) unused

    # ---- inline
    def inline(self, s):
        codes = []

        def keep(m):
            codes.append("<code>%s</code>" % self.code_inner(m.group(1)))
            return "\x00%d\x00" % (len(codes) - 1)

        s = re.sub(r"`([^`]+)`", keep, s)
        s = esc(s, quote=False)
        # links [text](url)
        def link(m):
            text, url = m.group(1), html.unescape(m.group(2)).strip()
            if re.match(r"https?://", url):
                return '<a href="%s" rel="noopener">%s</a>' % (esc(url), text)
            if url.startswith("#"):
                return '<a href="%s">%s</a>' % (esc(url), text)
            name = url.split("#")[0].split("/")[-1]
            target = self.link_md(name)
            return '<a href="%s">%s</a>' % (esc(target), text) if target else text
        s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, s)
        # bare urls (not already inside a tag attribute)
        s = re.sub(r'(?<![">=/\w])(https?://[^\s<>"\x00]+[^\s<>".,;:)\x00])',
                   lambda m: m.group(1) if "localhost" in m.group(1) else '<a href="%s" rel="noopener">%s</a>' % (m.group(1), m.group(1)), s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<![\w*])\*([^*\s][^*]*?)\*(?![\w*])", r"<em>\1</em>", s)
        s = re.sub(r"(?<![\w])_([^_\s][^_]*?)_(?![\w])", r"<em>\1</em>", s)
        if self.section_ref:
            def sec(m):
                u = self.section_ref(m.group(1))
                return '<a href="%s">%s</a>' % (esc(u), m.group(0)) if u else m.group(0)
            s = re.sub(r"§(\d+)(?![\d.]*\d)", sec, s)
        return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], s)

    def code_inner(self, c):
        c = esc(c, quote=False)
        name = c.strip()
        return c

    # ---- blocks
    def render(self, text):
        lines = text.split("\n")
        out, i, n = [], 0, len(lines)
        while i < n:
            ln = lines[i]
            if not ln.strip():
                i += 1
                continue
            m = re.match(r"^```(\w*)\s*$", ln)
            if m:
                j = i + 1
                while j < n and not lines[j].startswith("```"):
                    j += 1
                code = esc("\n".join(lines[i + 1:j]), quote=False)
                out.append("<pre><code>%s</code></pre>" % code)
                i = j + 1
                continue
            m = re.match(r"^(#{1,4})\s+(.*?)\s*#*\s*$", ln)
            if m:
                level = min(len(m.group(1)) + self.h_offset, 4)
                raw = m.group(2)
                hid = self.uid(slugify(raw))
                inner = self.inline(raw)
                if level in (2, 3):
                    self.heads.append((level, hid, re.sub(r"<[^>]+>", "", html.unescape(inner))))
                out.append('<h%d id="%s">%s</h%d>' % (level, hid, inner, level))
                i += 1
                continue
            if re.match(r"^\s*(---+|\*\*\*+)\s*$", ln):
                out.append("<hr>")
                i += 1
                continue
            if ln.startswith(">"):
                j = i
                buf = []
                while j < n and lines[j].startswith(">"):
                    buf.append(re.sub(r"^>\s?", "", lines[j]))
                    j += 1
                out.append("<blockquote>%s</blockquote>" % self.render("\n".join(buf)))
                i = j
                continue
            if ln.startswith("|") and i + 1 < n and re.match(r"^\|[\s:|-]+\|\s*$", lines[i + 1]):
                j = i + 2
                rows = []
                while j < n and lines[j].startswith("|"):
                    rows.append(self.cells(lines[j]))
                    j += 1
                head = self.cells(ln)
                t = ["<table><thead><tr>%s</tr></thead><tbody>" % "".join("<th>%s</th>" % self.inline(c) for c in head)]
                for r in rows:
                    t.append("<tr>%s</tr>" % "".join(
                        '<td data-label="%s">%s</td>' % (esc(re.sub(r"[*`]", "", head[k]) if k < len(head) else ""), self.inline(c))
                        for k, c in enumerate(r)))
                t.append("</tbody></table>")
                out.append("".join(t))
                i = j
                continue
            m = re.match(r"^(\s*)([-*]|\d+[.)])\s+", ln)
            if m:
                i = self.list_block(lines, i, out)
                continue
            # paragraph
            j = i
            buf = []
            while j < n and lines[j].strip() and not re.match(r"^(```|#{1,4}\s|>|\|)", lines[j]) \
                    and not re.match(r"^\s*([-*]|\d+[.)])\s+", lines[j]):
                buf.append(lines[j].rstrip("\n"))
                j += 1
            if not buf:  # safety: never loop forever
                buf = [ln]
                j = i + 1
            txt = "\n".join(buf)
            txt = re.sub(r" {2,}\n", "\x01", txt).replace("\n", " ")
            out.append("<p>%s</p>" % self.inline(txt).replace("\x01", "<br>"))
            i = j
        return "\n".join(out)

    @staticmethod
    def cells(line):
        line = line.strip()
        if line.startswith("|"):
            line = line[1:]
        if line.endswith("|"):
            line = line[:-1]
        return [c.strip() for c in re.split(r"(?<!\\)\|", line)]

    def list_block(self, lines, i, out):
        n = len(lines)
        m = re.match(r"^(\s*)([-*]|\d+[.)])\s+", lines[i])
        ordered = m.group(2)[0].isdigit()
        base = len(m.group(1))
        items = []
        while i < n:
            m = re.match(r"^(\s*)([-*]|\d+[.)])\s+(.*)$", lines[i])
            if m and len(m.group(1)) == base and m.group(2)[0].isdigit() == ordered:
                items.append([m.group(3)])
                i += 1
                # continuation lines (indented, not a new marker at base indent)
                while i < n:
                    l = lines[i]
                    if not l.strip():
                        # blank: continues the item only if the next non-blank is indented deeper than base
                        k = i
                        while k < n and not lines[k].strip():
                            k += 1
                        if k < n and len(lines[k]) - len(lines[k].lstrip()) > base and not re.match(r"^\s*([-*]|\d+[.)])\s+", lines[k]):
                            items[-1].append("")
                            i += 1
                            continue
                        break
                    ind = len(l) - len(l.lstrip())
                    if ind > base and not (re.match(r"^\s*([-*]|\d+[.)])\s+", l) and ind <= base):
                        items[-1].append(l.strip())
                        i += 1
                        continue
                    break
                # skip blank lines between items of the same list
                k = i
                while k < n and not lines[k].strip():
                    k += 1
                nm = re.match(r"^(\s*)([-*]|\d+[.)])\s+", lines[k]) if k < n else None
                if nm and len(nm.group(1)) == base and nm.group(2)[0].isdigit() == ordered:
                    i = k
                    continue
                break
            else:
                break
        tag = "ol" if ordered else "ul"
        lis = []
        for it in items:
            paras, cur = [], []
            for part in it:
                if part == "":
                    if cur:
                        paras.append(" ".join(cur))
                        cur = []
                else:
                    cur.append(part)
            if cur:
                paras.append(" ".join(cur))
            body = self.inline(paras[0]) + "".join("<p>%s</p>" % self.inline(p) for p in paras[1:])
            lis.append("<li>%s</li>" % body)
        out.append("<%s>%s</%s>" % (tag, "".join(lis), tag))
        return i

    def uid(self, s):
        base, k = s, 2
        while s in self.ids:
            s = "%s-%d" % (base, k)
            k += 1
        self.ids.add(s)
        return s


def strip_notes(text):
    """Remove author notes from a legal draft: leading blockquote, drafting notes, [CHECK ...] / [DECIDE ...]."""
    lines = text.split("\n")
    # title line
    title = None
    if lines and lines[0].startswith("# "):
        title = lines[0][2:].strip()
        lines = lines[1:]
    # leading blockquote block (DRAFT banner + placeholder note)
    k = 0
    while k < len(lines) and not lines[k].strip():
        k += 1
    if k < len(lines) and lines[k].startswith(">"):
        while k < len(lines) and (lines[k].startswith(">") or not lines[k].strip()):
            k += 1
    lines = lines[k:]
    text = "\n".join(lines)
    # drafting notes at the end
    m = re.search(r"\n(?:---+\s*\n)?#{2,3} Drafting notes[^\n]*\n.*\Z", text, re.S)
    if m:
        text = text[:m.start()] + "\n"
    # [CHECK ...] / [DECIDE ...] notes (bracket-balanced, may span lines); drop with the space before
    out, i = [], 0
    while i < len(text):
        m = re.compile(r"\*?\[(?:CHECK|DECIDE|Planned in G2)\b").match(text, i)
        if m:
            depth, j = 0, i
            while j < len(text):
                if text[j] == "[":
                    depth += 1
                elif text[j] == "]":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            while out and out[-1] in " \t":
                out.pop()
            if out and out[-1] == "\n" and j + 1 < len(text) and text[j + 1] == "\n":
                pass
            i = j + 1
            continue
        out.append(text[i])
        i += 1
    text = "".join(out)
    # inside the placeholders that stay: drop a trailing ": CHECK ..." / ", DECIDE ..." remark
    def clean(m):
        inner = re.sub(r"\s*[:,;]?\s*\b(?:CHECK|DECIDE|CONFIRM)\b[^\]]*$", "", m.group(1)).strip()
        return "[%s]" % inner
    text = re.sub(r"\[([^\[\]]*\b(?:CHECK|DECIDE|CONFIRM)\b[^\[\]]*)\]", clean, text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r" {2,}(?=\S)", lambda m: " " if False else m.group(0), text)
    return title, text


def mark_placeholders(htm):
    """Wrap remaining [PLACEHOLDER] brackets (outermost, balanced; not in code / tags) as dashed 'still to fill'."""
    parts = re.split(r"(<pre>.*?</pre>|<code>.*?</code>|<[^>]+>)", htm, flags=re.S)
    for k in range(0, len(parts), 2):
        t, out, i = parts[k], [], 0
        while i < len(t):
            if t[i] == "[":
                depth, j = 0, i
                while j < len(t):
                    depth += (t[j] == "[") - (t[j] == "]")
                    if depth == 0:
                        break
                    j += 1
                if j < len(t) and j - i < 300:
                    out.append('<span class="ph" title="To be filled before launch">%s</span>' % t[i:j + 1])
                    i = j + 1
                    continue
            out.append(t[i])
            i += 1
        parts[k] = "".join(out)
    return "".join(parts)


# ------------------------------------------------------------------ page chrome
class Site:
    def __init__(self, cfg, source):
        self.cfg, self.source = cfg, source
        self.pages = []          # (path, in_sitemap)
        self.guide = []          # (num, title, slug, md)
        self.guide_intro = ""

    def write(self, rel, content, sitemap=True):
        p = HERE / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        if sitemap:
            self.pages.append(rel)

    # ---- buttons: empty link = "Coming soon"
    def btn(self, url, label, cls, soon_label="Coming soon"):
        if url:
            return '<a class="btn %s" href="%s" rel="noopener">%s</a>' % (cls, esc(url, quote=True), label)
        return '<span class="btn %s is-soon" title="The store opens soon">%s</span>' % (cls, soon_label)

    def buy(self, cls="buy", price=True):
        """Hero button: to the price cards (three packs)."""
        return '<a class="btn %s" href="#buy">Buy · from %s</a>' % (cls, esc(self.cfg.get("price_from") or self.cfg["price"]))

    def packs(self):
        """The price cards of the packs on sale (site.json packs_on; AV-first launch: only av)."""
        c = self.cfg
        cards = {"av": ("AV", c.get("price_visuals", ""), "Core + AV + MIDI", c.get("buy_visuals_url")),
                 "lights": ("Lights Control", c.get("price_lights", ""), "Core + Lights + MIDI", c.get("buy_lights_url")),
                 "full": ("Full", c["price"], "Core + AV + Lights + MIDI", c.get("buy_url"))}
        on = [k for k in c.get("packs_on", ["av", "lights", "full"]) if k in cards]
        return '<div class="packs%s">%s</div>' % (" one" if len(on) == 1 else "", "".join(self.pack(*cards[k]) for k in on))

    def pack(self, name, price, parts, url):
        return ('<div class="pack"><h3>%s</h3><div class="amount">%s</div><p class="parts">%s</p>%s</div>'
                % (esc(name), esc(price), parts, self.btn(url, "Buy %s" % esc(name), "buy")))

    def trial(self):
        return self.btn(self.cfg.get("trial_url"), "Try free for %s days" % self.cfg["trial_days"], "",
                        "Free trial coming soon")

    def head(self, root, current):
        nav = [("Guide", "guide/", "guide"), ("Changelog", "changelog/", "changelog"),
               ("Requirements", "#requirements", "req"), ("Support", "support/", "support")]
        def href(h):
            return (root + "index.html" + h) if h.startswith("#") else root + h
        navhtml = "".join('<a href="%s"%s>%s</a>' % (href(h) if not h.startswith("#") else root + h,
                                                      ' aria-current="page"' if k == current else "", t)
                          for t, h, k in nav)
        sheet = "".join('<a href="%s">%s</a>' % (root + h, t) for t, h, k in nav)
        buy = self.btn(self.cfg.get("buy_url"), 'Buy<span class="hp">&nbsp;· %s</span>' % esc(self.cfg["price"]), "buy sm")
        return ('<header class="head"><div class="wrap">'
                '<a class="mark" href="%s" aria-label="Backline, home">%s Backline</a>'
                '<nav class="nav" aria-label="Main">%s</nav><span class="spacer"></span>%s'
                '<details class="menu"><summary aria-label="Menu"><svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">'
                '<path d="M2 5h14M2 9h14M2 13h14" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg></summary>'
                '<div class="sheet">%s</div></details></div></header>') % (root or "./", MARK, navhtml, buy, sheet)

    def foot(self, root):
        c = self.cfg
        mail = ('<a href="mailto:%s">%s</a>' % (esc(c["support_email"]), esc(c["support_email"]))
                if c.get("support_email") else '<a href="%ssupport/">Contact</a>' % root)
        portal = ('<li><a href="%s" rel="noopener">Customer portal</a></li>' % esc(c["portal_url"])) if c.get("portal_url") else ""
        buy = ('<li><a href="%s" rel="noopener">Buy</a></li>' % esc(c["buy_url"])) if c.get("buy_url") else \
            '<li><a href="%sindex.html#buy">Buy</a></li>' % root
        return ('<footer class="foot"><div class="wrap">'
                '<div class="about"><a class="mark" href="%(r)s%(home)s">%(m)s Backline</a>'
                '<p class="small">Built and played live by %(o)s, Paris.</p></div>'
                '<div><h3>Product</h3><ul><li><a href="%(r)sguide/">Guide</a></li><li><a href="%(r)schangelog/">Changelog</a></li>'
                '<li><a href="%(r)sindex.html#requirements">Requirements</a></li>%(buy)s</ul></div>'
                '<div><h3>Legal</h3><ul><li><a href="%(r)seula/">EULA</a></li><li><a href="%(r)sprivacy/">Privacy</a></li>'
                '<li><a href="%(r)sterms/">Terms of sale</a></li></ul></div>'
                '<div><h3>Support</h3><ul><li><a href="%(r)ssupport/">Support</a></li><li>%(mail)s</li>%(portal)s</ul></div>'
                '<p class="legal">TouchDesigner is a product of Derivative Inc.; this product is independent of it. © 2026 %(o)s.</p>'
                '</div></footer>') % dict(r=root, home="" if root else "./", m=MARK, o=esc(c["owner"]), buy=buy, mail=mail, portal=portal)

    def page(self, rel, title, desc, body, current="", noindex=False, sitemap=True):
        depth = rel.count("/")
        root = "../" * depth
        c = self.cfg
        canon = ""
        if c.get("site_url"):
            canon = '<link rel="canonical" href="%s/%s">' % (c["site_url"].rstrip("/"), rel.replace("index.html", ""))
        robots = '<meta name="robots" content="noindex">' if noindex else ""
        doc = ('<!doctype html>\n<html lang="en" data-theme="umber" data-accent="azure">\n<head>\n<meta charset="utf-8">\n'
               '<meta name="viewport" content="width=device-width, initial-scale=1">\n<meta name="theme-color" content="#0c0a09">\n'
               '<title>%(t)s</title>\n<meta name="description" content="%(d)s">\n'
               '<meta property="og:title" content="%(t)s"><meta property="og:description" content="%(d)s"><meta property="og:type" content="website">\n'
               '%(robots)s%(canon)s<link rel="icon" href="%(r)sassets/favicon.svg" type="image/svg+xml">\n'
               '<link rel="stylesheet" href="%(r)sassets/site.css">\n</head>\n<body>\n'
               '<a class="skip" href="#main">Skip to content</a>\n%(head)s\n%(body)s\n%(foot)s\n</body>\n</html>\n') % dict(
            t=esc(title), d=esc(desc), robots=robots, canon=canon, r=root, head=self.head(root, current),
            body=body.replace("@@R@@", root), foot=self.foot(root))
        self.write(rel, doc, sitemap and not noindex)

    # ---- docs template: sidebar + article + toc
    def doc_page(self, rel, title, lead, article, side, toc, current, pager=None, desc=None, side_title="", extra_top=""):
        root = "../" * rel.count("/")
        side_html = "".join(side)
        menu = '<details class="doc-menu"><summary>%s</summary><nav class="side" aria-label="Pages (phone)">%s</nav></details>' % (
            esc(side_title or "Contents"), side_html)
        toc_html = ('<nav class="toc" aria-label="On this page"><b>On this page</b>%s</nav>' % "".join(
            '<a href="#%s">%s</a>' % (i, esc(t)) for i, t in toc)) if toc else '<div aria-hidden="true"></div>'
        pager_html = ""
        if pager:
            prev, nxt = pager
            pager_html = '<nav class="pager" aria-label="Pages">%s%s</nav>' % (
                ('<a href="%s"><small>Previous</small>%s</a>' % (prev[0], esc(prev[1]))) if prev else "<span></span>",
                ('<a class="nx" href="%s"><small>Next</small>%s</a>' % (nxt[0], esc(nxt[1]))) if nxt else "<span></span>")
        body = ('<main id="main" class="docs"><nav class="side" aria-label="Pages">%s</nav><article class="doc">%s'
                '<h1>%s</h1>%s%s%s%s</article>%s</main>') % (
            side_html, menu, esc(title), ('<p class="lead">%s</p>' % lead) if lead else "", extra_top, article, pager_html, toc_html)
        self.page(rel, "%s · Backline" % title, desc or re.sub(r"<[^>]+>", "", lead) or title, body, current)

    # ---- landing + small pages
    def landing(self):
        c = self.cfg
        t = (HERE / "templates" / "landing.html").read_text(encoding="utf-8")
        v = c.get("video", "")
        if v.endswith(".mp4"):
            p = c.get("video_poster", "")
            poster = ' poster="@@R@@%s"' % esc(p) if p else ""
            video = ('<div class="mon"><video controls playsinline preload="none"%s src="@@R@@%s"></video>'
                     '<span class="tag pgm"><b>PGM</b> demo reel</span></div>') % (poster, esc(v))
        elif v:
            video = ('<div class="mon"><iframe src="%s" title="Backline demo video" loading="lazy" allow="fullscreen; picture-in-picture" '
                     'allowfullscreen></iframe><span class="tag pgm"><b>PGM</b> demo reel</span></div>') % esc(v)
        else:
            video = ('<div class="mon"><div class="slot"><span class="note">Demo video coming soon</span></div>'
                     '<span class="tag pgm"><b>PGM</b> demo reel</span></div>')
        s = c.get("screenshot", "")
        alt = c.get("screenshot_alt") or "The PERFORM screen: program and preview, scenes and effects, parameters, status bar"
        w, h = img_size(HERE / s) if s else (1920, 1080)
        shot = ('<figure class="shot" style="margin-inline:0"><img src="@@R@@%s" alt="%s" width="%d" height="%d" loading="lazy">'
                '</figure>' % (esc(s), esc(alt), w, h)) if s else ""
        rep = {"%%BUY_BTN%%": self.buy(), "%%BUY_BTN_PRICE%%": self.btn(c.get("buy_url"), "Buy on Polar", "buy"),
               "%%PACKS%%": self.packs(),
               "%%TRIAL_BTN%%": self.trial(), "%%VIDEO%%": video, "%%SCREENSHOT%%": shot,
               "%%GRACE%%": str(c["grace_days"]), "%%PRICE%%": esc(c["price"]), "%%TRIAL_DAYS%%": str(c["trial_days"])}
        for k, val in rep.items():
            t = t.replace(k, val)
        self.page("index.html", "Backline · play your TouchDesigner visuals live from one controller",
                  "Backline: a show system for TouchDesigner. Scenes, effects and MIDI on one preview / program transport. "
                  "From %s, perpetual licence, 14-day free trial." % (c.get("price_from") or c["price"]), t)

    def support(self):
        c = self.cfg
        t = (HERE / "templates" / "support.html").read_text(encoding="utf-8")
        mail = ('<p><a href="mailto:%s">%s</a></p><p>Replies come from a person, not a bot.</p>' % (esc(c["support_email"]), esc(c["support_email"]))
                if c.get("support_email") else '<p>The support address is coming with the launch. Until then use <strong>More › Report a problem…</strong> in the app.</p>')
        portal = ('<p><a class="btn sm" href="%s" rel="noopener">Open the customer portal</a></p>' % esc(c["portal_url"])
                  if c.get("portal_url") else '<p class="muted">Customer portal link: coming soon.</p>')
        t = t.replace("%%SUPPORT_MAIL%%", mail).replace("%%PORTAL%%", portal)
        self.page("support/index.html", "Support · Backline", "Backline support: email, in-app problem report, licence and computers.", t, "support")

    def thanks(self):
        t = (HERE / "templates" / "thanks.html").read_text(encoding="utf-8")
        self.page("thanks/index.html", "Thank you · Backline", "Your Backline order: what happens next.", t, noindex=True, sitemap=False)

    def notfound(self):
        bp = self.cfg.get("base_path", "").rstrip("/")
        body = ('<main id="main" class="docs" style="grid-template-columns:minmax(0,var(--read))"><article class="doc"><h1>Page not found</h1>'
                '<p class="lead">This page does not exist. <a href="%s/">Back to the Backline home page</a>.</p></article></main>') % bp
        doc = ('<!doctype html>\n<html lang="en" data-theme="umber"><head><meta charset="utf-8">'
               '<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">'
               '<title>Page not found · Backline</title><link rel="stylesheet" href="%s/assets/site.css"></head><body>'
               '<header class="head"><div class="wrap"><a class="mark" href="%s/">%s Backline</a></div></header>%s</body></html>\n') % (
            bp, bp, MARK, body)
        self.write("404.html", doc, sitemap=False)

    # ---- guide
    def build_guide(self):
        text = (self.source / "docs" / "GUIDE.md").read_text(encoding="utf-8")
        parts = re.split(r"(?m)^## ", text)
        intro = parts[0]
        secs = []
        for p in parts[1:]:
            head, _, body = p.partition("\n")
            m = re.match(r"(\d+)\.?\s+(.*)", head.strip())
            num, title = (m.group(1), m.group(2)) if m else ("", head.strip())
            if num in set(map(str, self.cfg.get("guide_skip", []))):
                continue
            secs.append((num, title, slugify(title), body))
        # Buyer flow wording (Matteo's live test, 2026-11-25). Applied only while docs/GUIDE.md still has the old text:
        # once the product guide carries the new wording this does nothing.
        for k, (n, t, sl, body) in enumerate(secs):
            for old, new in GUIDE_PATCH:
                if n == "0" and old in body:
                    secs[k] = (n, t, sl, body.replace(old, new))
        by_num = {n: "@@R@@guide/%s/" % s for n, _, s, _ in secs}
        # which relative .md links exist as site pages
        def link_md(name):
            if name == "GUIDE.md":
                return "@@R@@guide/"
            if name in LEGAL_REF:
                return "@@R@@" + LEGAL_REF[name] + "/"
            return None
        def section_ref(n):
            return by_num.get(n)
        side_items = ['<h3>Guide</h3><ul><li><a href="@@R@@guide/">Overview</a></li>%s</ul>']
        def side_for(cur):
            lis = ['<li><a href="@@R@@guide/"%s>Overview</a></li>' % (' aria-current="page"' if cur == "" else "")]
            for n, t, s, _ in secs:
                lis.append('<li><a href="@@R@@guide/%s/"%s><span class="n">%s</span>%s</a></li>' % (
                    s, ' aria-current="page"' if cur == s else "", esc(n), esc(t)))
            return ['<h3>Guide</h3><ul>%s</ul><h3>Also</h3><ul><li><a href="@@R@@changelog/">Changelog</a></li>'
                    '<li><a href="@@R@@support/">Support</a></li></ul>' % "".join(lis)]
        order = [("", "Overview")] + [(s, "%s %s" % (n, t) if n else t) for n, t, s, _ in secs]
        def pager_for(k):
            def mk(idx):
                s, label = order[idx]
                return ("@@R@@guide/%s" % (s + "/" if s else ""), label)
            return (mk(k - 1) if k > 0 else None, mk(k + 1) if k + 1 < len(order) else None)
        # overview page
        md = Md(link_md=link_md, section_ref=section_ref)
        intro_body = re.sub(r"^# .*\n", "", intro, count=1)
        intro_html = md.render(re.split(r"\s*Topic manuals", intro_body.strip())[0].strip())  # first paragraph only: the rest points to internal manuals
        cards = "".join('<li><a href="@@R@@guide/%s/"><strong>%s %s</strong></a></li>' % (s, esc(n), esc(t)) for n, t, s, _ in secs)
        notes = ('<div class="callout"><b>Note.</b> This is the working guide of the product. Some parts still speak of the beta; '
                 'a guide written for buyers comes with version 1.0. Where it says "Windows not yet tested", that is the current state.</div>')
        article = intro_html + notes + '<h2 id="sections">Sections</h2><ol start="0">%s</ol>' % cards
        self.doc_page("guide/index.html", "Guide", "",
                      article.replace("@@R@@", "../"), [x.replace("@@R@@", "../") for x in side_for("")], [], "guide",
                      pager=tuple(((a[0].replace("@@R@@", "../"), a[1]) if a else None) for a in pager_for(0)),
                      desc="Backline guide: how the system is put together, how to play a show, how to add your own scenes, effects, fixtures and controllers.",
                      side_title="Guide contents")
        for k, (n, t, s, body) in enumerate(secs, start=1):
            md = Md(link_md=link_md, section_ref=section_ref, h_offset=-1)
            html_body = md.render(body.strip())
            toc = [(i, tx) for (lv, i, tx) in md.heads if lv == 2]
            lead = ""
            self.doc_page("guide/%s/index.html" % s, t, lead, html_body.replace("@@R@@", "../../"),
                          [x.replace("@@R@@", "../../") for x in side_for(s)], toc, "guide",
                          pager=tuple(((a[0].replace("@@R@@", "../../"), a[1]) if a else None) for a in pager_for(k)),
                          desc="Backline guide: %s." % t, side_title="Guide contents")
        self.guide = secs

    # ---- changelog
    def build_changelog(self):
        text = (self.source / "CHANGELOG.md").read_text(encoding="utf-8")
        blocks = re.split(r"(?m)^## ", text)[1:]
        md = Md()
        rels, sidev = [], []
        formats = None
        for b in blocks:
            head, _, body = b.partition("\n")
            m = re.match(r"([\d.]+)\s+—\s+(\d{4}-\d{2}-\d{2})\s*(?:\((.*?)\))?", head.strip())
            if not m:
                continue  # unreleased entries
            ver, date, label = m.groups()
            items, cur = [], None
            for ln in body.split("\n"):
                im = re.match(r"^- \*\*(\w+)\*\*:?\s*(.*)$", ln)
                if im:
                    cur = [im.group(1), [im.group(2)]]
                    items.append(cur)
                elif ln.startswith("  ") and cur:
                    cur[1].append(ln.strip())
                elif ln.startswith("- ") and not im:
                    cur = ["Note", [ln[2:]]]
                    items.append(cur)
            lis = "".join('<li><span class="chip %s">%s</span><span>%s</span></li>' % (esc(k), esc(k), md.inline(" ".join(v)))
                          for k, v in items)
            vid = "v" + ver.replace(".", "-")
            rels.append('<section class="rel" id="%s"><header><h2>%s</h2><time datetime="%s">%s</time>%s</header><ul>%s</ul></section>' % (
                vid, esc(ver), date, date, ('<span class="beta">%s</span>' % esc(label)) if label else "", lis))
            sidev.append('<li><a href="#%s">%s</a></li>' % (vid, esc(ver)))
            if formats is None:
                for k, v in items:
                    if k == "Formats":
                        formats = md.inline(" ".join(v))
        side = ['<h3>Versions</h3><ul>%s</ul><h3>Also</h3><ul><li><a href="../guide/">Guide</a></li></ul>' % "".join(sidev)]
        lead = "Every release, newest first."
        body = "".join(rels)
        toc_note = ('<nav class="toc" aria-label="Formats"><b>Formats</b><span class="muted" style="font-size:13px">Old show files '
                    'upgrade by themselves; newer ones are refused. Latest: %s</span></nav>' % (formats or "—"))
        doc = ('<main id="main" class="docs"><nav class="side" aria-label="Versions">%s</nav><article class="doc">'
               '<details class="doc-menu"><summary>Versions</summary><nav class="side" aria-label="Versions (phone)">%s</nav></details>'
               '<h1>Changelog</h1><p class="lead">%s</p>%s</article>%s</main>') % (side[0], side[0], lead, body, toc_note)
        self.page("changelog/index.html", "Changelog · Backline", "Every Backline release, newest first: fixed, added, changed, file formats.", doc, "changelog")

    # ---- legal
    def build_legal(self):
        for key, fname, title, label in LEGAL:
            raw = (self.source / "docs" / "legal" / fname).read_text(encoding="utf-8")
            _, text = strip_notes(raw)
            md = Md(link_md=lambda name: ("@@R@@" + LEGAL_REF[name] + "/") if name in LEGAL_REF else None)
            # `EULA.md` etc. in code spans -> links to the sibling page
            def ref(m):
                return "[%s](%s)" % (m.group(2), m.group(1))
            text = re.sub(r"`(EULA\.md|PRIVACY\.md|TERMS_OF_SALE\.md)`", lambda m: "[%s](%s)" % (
                {"EULA.md": "EULA", "PRIVACY.md": "Privacy policy", "TERMS_OF_SALE.md": "Terms of sale"}[m.group(1)], m.group(1)), text)
            body = mark_placeholders(md.render(text.strip()))
            toc = [(i, tx) for (lv, i, tx) in md.heads if lv == 2]
            side = ['<h3>Legal</h3><ul>%s</ul>' % "".join(
                '<li><a href="@@R@@%s/"%s>%s</a></li>' % (k, ' aria-current="page"' if k == key else "", l) for k, _, _, l in LEGAL)]
            draft = ""
            if self.cfg.get("legal_draft", True):
                draft = ('<div class="draft"><b>Draft.</b> This text is being checked by a lawyer and is not in force yet. '
                         'Parts marked <span class="ph">[like this]</span> are still to be filled in.</div>')
            lead = "Version 1.0 · draft, not yet in force." if self.cfg.get("legal_draft", True) else "Version 1.0."
            short = ""
            if key == "eula":
                short = ('<div class="callout"><b>In short:</b> one licence, 2 computers of yours; your scenes, looks and shows are yours; '
                         'TouchDesigner is licensed separately by Derivative.</div>')
            self.doc_page("%s/index.html" % key, title, lead, body.replace("@@R@@", "../"),
                          [x.replace("@@R@@", "../") for x in side], toc, "legal", extra_top=draft + short,
                          desc="Backline %s." % title.lower(), side_title="Legal")

    def sitemap(self):
        u = self.cfg.get("site_url", "").rstrip("/")
        if not u:
            p = HERE / "sitemap.xml"
            if p.exists():
                p.unlink()
            return
        urls = "".join("<url><loc>%s/%s</loc></url>" % (u, p.replace("index.html", "")) for p in sorted(set(self.pages)))
        (HERE / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">%s</urlset>\n' % urls, encoding="utf-8")
        (HERE / "robots.txt").write_text("User-agent: *\nAllow: /\nSitemap: %s/sitemap.xml\n" % u, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default=str(HERE.parent / "av_infrastructure"), help="path of the product repo (docs are read from it)")
    a = ap.parse_args()
    source = Path(a.source).resolve()
    need = [source / "docs" / "GUIDE.md", source / "CHANGELOG.md"] + [source / "docs" / "legal" / f for _, f, _, _ in LEGAL]
    miss = [str(p) for p in need if not p.is_file()]
    if miss:
        sys.exit("Product repo not found / files missing (use --source):\n  " + "\n  ".join(miss))
    cfg = json.loads((HERE / "site.json").read_text(encoding="utf-8"))
    # clean generated pages (never assets / templates / tools)
    for d in ("guide", "changelog", "eula", "privacy", "terms", "support", "thanks"):
        shutil.rmtree(HERE / d, ignore_errors=True)
    s = Site(cfg, source)
    s.landing(); s.build_guide(); s.build_changelog(); s.build_legal(); s.support(); s.thanks(); s.notfound(); s.sitemap()
    (HERE / ".nojekyll").write_text("", encoding="utf-8")
    print("built %d pages from %s" % (len(s.pages), source))


if __name__ == "__main__":
    main()
