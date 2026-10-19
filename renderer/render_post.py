# -*- coding: utf-8 -*-
"""Render an @ayushi.pixel carousel from a JSON spec into 1080x1350 slides.

Usage: python3 render_post.py spec.json OUT_DIR [--png]
Writes slide-01.jpg ... (JPEG, quality 92) and, with --png, slide-01.png too.

Spec formats (all text, no markup beyond what is described):
  {"format": "hit", "cover": ["line 1", "line 2", "last line in italics"],
   "slides": [ {"type": "text", "p": ["para 1", "para 2"]},
               {"type": "quote", "setup": "...", "quote": "...", "follow": "..."} ... ]}
      In hit paragraphs, [[key phrase]] becomes purple italics. Slide count = 1 + len(slides).
  {"format": "cb", "hint": "Swipe to see who stays",
   "cards": ["cover: line 1\\nline 2 with **purple bold**", "card 2 with **purple bold**", ...,
             "lead line\\n-> item\\n-> item\\nclosing image line"]}
  {"format": "founder", "slides": [["grey part", "white part"], ...]}
"""
import asyncio, base64, html, json, os, re, sys
from playwright.async_api import async_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
A = HERE + '/assets/'


def b64(name):
    return base64.b64encode(open(A + name, 'rb').read()).decode()


def face(family, weight, style, name, fmt='woff2'):
    mime = 'font/woff2' if fmt == 'woff2' else 'font/otf'
    return "@font-face{font-family:'%s';font-weight:%s;font-style:%s;src:url(data:%s;base64,%s) format('%s');}" % (family, weight, style, mime, b64(name), 'woff2' if fmt == 'woff2' else 'opentype')


def nb(t):
    return re.sub(r' (\S+)$', ' \\1', t.strip())


# ---------------- How I Think ----------------
HIT_FONTS = ''.join([
    face('Instrument Serif', 400, 'normal', 'instrument-serif-latin-400-normal.woff2'),
    face('Instrument Serif', 400, 'italic', 'instrument-serif-latin-400-italic.woff2'),
    face('Newsreader', 400, 'normal', 'newsreader-latin-400-normal.woff2'),
    face('Newsreader', 400, 'italic', 'newsreader-latin-400-italic.woff2'),
    face('Inter', 500, 'normal', 'inter-latin-500-normal.woff2'),
])


def hit_key(t):
    t = html.escape(nb(t))
    return re.sub(r'\[\[(.+?)\]\]', r'<em class="k">\1</em>', t)


def hit_page(i, total, css, body, cover=False):
    right = 'Save this' if i == total else 'Swipe →'
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{HIT_FONTS}
html,body{{margin:0;background:#fff}}
.s{{width:1080px;height:1350px;position:relative;background:{'#3d3fcc' if cover else '#fff'};overflow:hidden}}
.l{{position:absolute;font-family:'Inter';font-weight:500;font-size:21px;letter-spacing:.24em;text-transform:uppercase;color:{'#fff' if cover else '#111'};line-height:1}}
.rule{{position:absolute;left:96px;right:96px;height:1px;background:{'rgba(255,255,255,.35)' if cover else 'rgba(17,17,17,.18)'}}}
em.k{{font-style:italic;color:#3d3fcc}} p{{margin:0}}
{css}
</style></head><body><div class="s">
<div class="l" style="top:92px;left:96px">How I Think</div>
<div class="l" style="top:92px;right:96px">Nº {i:02d} / {total:02d}</div>
<div class="rule" style="top:140px"></div><div class="rule" style="bottom:140px"></div>
<div class="l" style="bottom:92px;left:96px">Ayushi Jain</div>
<div class="l" style="bottom:92px;right:96px">{right}</div>
{body}
</div></body></html>"""


def hit_pages(spec):
    slides = spec['slides']
    total = 1 + len(slides)
    lines = spec['cover']
    h = '<br>'.join(html.escape(l) if k < len(lines) - 1 else '<em style="font-style:italic">%s</em>' % html.escape(l) for k, l in enumerate(lines))
    out = [hit_page(1, total, ".h{position:absolute;left:92px;right:92px;bottom:250px;font-family:'Instrument Serif';font-size:150px;line-height:.98;letter-spacing:-3px;color:#fff}", f'<div class="h">{h}</div>', cover=True)]
    textcss = ".t{position:absolute;left:96px;right:110px;top:140px;bottom:140px;display:flex;flex-direction:column;justify-content:center;font-family:'Newsreader';font-size:50px;line-height:1.34;letter-spacing:-.4px;color:#111;text-wrap:pretty}.t p+p{margin-top:44px}"
    quotecss = ".qa{position:absolute;left:96px;right:110px;top:260px;font-family:'Newsreader';font-size:40px;color:#444;line-height:1.3}.qq{position:absolute;left:96px;right:96px;top:480px;font-family:'Instrument Serif';font-style:italic;font-size:118px;line-height:1;letter-spacing:-2px;color:#3d3fcc}.qc{position:absolute;left:96px;right:110px;top:1000px;font-family:'Newsreader';font-size:40px;color:#444;line-height:1.3}"
    for n, s in enumerate(slides, start=2):
        if s.get('type') == 'quote':
            body = f'<div class="qa">{html.escape(s["setup"])}</div><div class="qq">{html.escape(s["quote"])}</div><div class="qc">{html.escape(s["follow"])}</div>'
            out.append(hit_page(n, total, quotecss, body))
        else:
            body = '<div class="t">' + ''.join(f'<p>{hit_key(p)}</p>' for p in s['p']) + '</div>'
            out.append(hit_page(n, total, textcss, body))
    return out


# ---------------- Campaign Breakdown (tweet style, light) ----------------
CB_FONTS = ''.join([
    face('Inter Display', 400, 'normal', 'InterDisplay-Regular.otf', 'otf'),
    face('Inter Display', 500, 'normal', 'InterDisplay-Medium.otf', 'otf'),
    face('Inter Display', 600, 'normal', 'InterDisplay-SemiBold.otf', 'otf'),
    face('Inter Display', 700, 'normal', 'InterDisplay-Bold.otf', 'otf'),
])


def cb_page(i, total, text, cover, hint):
    AV = b64('avatar.png')
    parts = text.split('\n')

    def fmt(x):
        x = html.escape(x.replace('->', '→'))
        return re.sub(r'\*\*(.+?)\*\*', r'<b class="p">\1</b>', x)
    if cover:
        t = '<p class="c1">%s</p><p class="c2">%s</p><p class="hint">%s →</p>' % (fmt(parts[0]), fmt(parts[1]) if len(parts) > 1 else '', html.escape(hint))
    elif len(parts) > 1:
        t = '<p>%s</p>' % fmt(parts[0])
        t += ''.join('<p class="ln">%s</p>' % fmt(x) for x in parts[1:-1])
        t += '<p class="end">%s</p>' % fmt(parts[-1])
    else:
        t = '<p>%s</p>' % fmt(text)
    pct = i / total * 100
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{CB_FONTS}
html,body{{margin:0;background:#FAFAFA}}
.s{{width:1080px;height:1350px;position:relative;background:#FAFAFA;overflow:hidden;font-family:'Inter Display'}}
.av{{position:absolute;left:90px;top:84px;width:112px;height:112px;border-radius:50%;border:3px solid #d9d9d9;overflow:hidden;box-sizing:border-box}}
.av img{{width:100%;height:100%;object-fit:cover}}
.nm{{position:absolute;left:232px;top:100px;font-size:34px;font-weight:700;color:#111;line-height:1}}
.hdl{{position:absolute;left:232px;top:148px;font-size:30px;color:#9a9a9a;line-height:1}}
.tx{{position:absolute;left:90px;right:90px;top:270px;bottom:200px;display:flex;flex-direction:column;justify-content:center;font-size:{'54px' if cover else '50px'};line-height:{1.5 if cover else 1.46};color:#111;letter-spacing:-0.01em;text-wrap:pretty}}
.tx p{{margin:0 0 {'34px' if cover else '30px'} 0}}
.c1{{font-weight:700}} .c2{{font-weight:400}}
b.p{{color:#3d3fcc;font-weight:700}}
.hint{{color:#3d3fcc;font-size:34px;font-weight:600;margin-top:30px}}
.ln{{margin-bottom:20px!important}}
.end{{margin-top:34px!important;color:#444}}
.bar{{position:absolute;left:90px;right:190px;bottom:72px;height:10px;border-radius:6px;background:#e4e4e4}}
.bar i{{display:block;height:100%;width:{pct:.1f}%;border-radius:6px;background:#3d3fcc}}
.ct{{position:absolute;right:90px;bottom:56px;font-size:32px;color:#9a9a9a}}
</style></head><body><div class="s">
<div class="av"><img src="data:image/png;base64,{AV}"></div>
<div class="nm">Ayushi Jain</div><div class="hdl">@ayushi.pixel</div>
<div class="tx">{t}</div>
<div class="bar"><i></i></div><div class="ct">{i}/{total}</div>
</div></body></html>"""


def cb_pages(spec):
    cards = spec['cards']
    return [cb_page(i, len(cards), t, i == 1, spec.get('hint', 'Swipe')) for i, t in enumerate(cards, 1)]


# ---------------- Founder (dark, Poppins grey + white) ----------------
FD_FONTS = ''.join([face('Poppins', 500, 'normal', 'poppins-latin-500-normal.woff2'), face('Poppins', 600, 'normal', 'poppins-latin-600-normal.woff2')])


def fsz(n):
    return 112 if n <= 25 else 98 if n <= 50 else 86 if n <= 75 else 76 if n <= 100 else 68 if n <= 125 else 62


def founder_page(w, a, i, total):
    n = len(w) + len(a)
    a_html = ('<span class="w"> %s</span>' % html.escape(nb(a))) if a else ''
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{FD_FONTS}
html,body{{margin:0;background:#000}}
.s{{width:1080px;height:1350px;position:relative;background:#000;overflow:hidden;font-family:'Poppins'}}
.frame{{position:absolute;left:34px;right:34px;top:34px;bottom:34px;border:1.5px solid #262626;border-radius:44px;background:#000}}
.grid2{{position:absolute;left:35px;right:35px;top:35px;bottom:35px;border-radius:43px;background-image:linear-gradient(rgba(255,255,255,.05) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.05) 1px,transparent 1px);background-size:90px 90px;background-position:-35px -35px;overflow:hidden}}
.top{{position:absolute;left:100px;top:96px;font-size:24px;letter-spacing:.14em;color:#777;font-weight:500;text-transform:uppercase}}
.t{{position:absolute;left:100px;right:100px;top:150px;bottom:190px;display:flex;align-items:center}}
.t p{{margin:0;font-weight:600;font-size:{fsz(n)}px;line-height:1.14;letter-spacing:-0.025em;color:#5c5c5c}}
.t .w{{color:#fff}}
.pill{{position:absolute;right:92px;bottom:92px;border:1.5px solid #333;border-radius:40px;padding:14px 28px;font-size:24px;letter-spacing:.12em;color:#9a9a9a;font-weight:500}}
.ft{{position:absolute;left:100px;bottom:106px;font-size:24px;letter-spacing:.06em;color:#777;font-weight:500}}
</style></head><body><div class="s"><div class="frame"></div><div class="grid2"></div>
<div class="top">Brand advisor &amp; strategist</div>
<div class="t"><p>{html.escape(w if a else nb(w))}{a_html}</p></div>
<div class="ft">@ayushi.pixel</div>
<div class="pill">{i:02d} OF {total:02d}</div>
</div></body></html>"""


def founder_pages(spec):
    sl = spec['slides']
    return [founder_page(w, a, i, len(sl)) for i, (w, a) in enumerate(sl, 1)]


async def main(spec_path, out_dir, png):
    spec = json.load(open(spec_path, encoding='utf-8'))
    pages = {'hit': hit_pages, 'cb': cb_pages, 'founder': founder_pages}[spec['format']](spec)
    os.makedirs(out_dir, exist_ok=True)
    from PIL import Image
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={'width': 1080, 'height': 1350})
        for i, h in enumerate(pages, 1):
            await pg.set_content(h)
            await pg.evaluate('document.fonts.ready')
            await pg.wait_for_timeout(250)
            png_path = f'{out_dir}/slide-{i:02d}.png'
            await pg.screenshot(path=png_path)
            Image.open(png_path).convert('RGB').save(f'{out_dir}/slide-{i:02d}.jpg', quality=92)
            if not png:
                os.remove(png_path)
        await b.close()
    print('rendered', len(pages), 'slides to', out_dir)

if __name__ == '__main__':
    asyncio.run(main(sys.argv[1], sys.argv[2], '--png' in sys.argv))
