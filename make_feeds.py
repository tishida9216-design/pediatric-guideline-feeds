#!/usr/bin/env python3
"""学会のガイドライン掲載ページを巡回し、新しく増えたリンクをRSSにする。
初回は既存リンクを「既読」として記録するだけで、フィードには載せない。"""
import json, re, os, sys, time, html, hashlib, urllib.parse, urllib.request
from datetime import datetime, timezone
from email.utils import format_datetime
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(ROOT, 'state'); OUT = os.path.join(ROOT, 'docs')
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15'
KEY = re.compile(r'ガイドライン|ガイド|指針|手引|提言|見解|声明|マニュアル|診療|診断基準|考え方|推奨|コンセンサス|Q&A|Ｑ＆Ａ|guideline', re.I)
SKIP = re.compile(r'COI|利益相反|決算|予算|議事録|名簿|入会|会費|プライバシー|サイトマップ|ログイン|login|mailto:|tel:|javascript:', re.I)
MAX_ITEMS = 60

def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read(); ct = r.headers.get('Content-Type','')
    m = re.search(r'charset=([\w-]+)', ct) or re.search(rb'charset=["\']?([\w-]+)', raw[:3000])
    enc = (m.group(1).decode() if isinstance(m.group(1), bytes) else m.group(1)) if m else 'utf-8'
    enc = {'shift_jis':'cp932','sjis':'cp932','x-sjis':'cp932','euc-jp':'euc_jp'}.get(enc.lower(), enc)
    try: return raw.decode(enc, errors='replace')
    except LookupError: return raw.decode('utf-8', errors='replace')

GENERIC = re.compile(r'^(pdf|PDF.*|こちら|ここ|ダウンロード|全文.*|詳細.*|詳しくはこちら|→|>|》|クリック|閲覧|本文)$')

def label_for(a):
    lab = ' '.join(a.get_text(' ').split())
    if lab and not GENERIC.match(lab) and len(lab) >= 4:
        return lab
    for anc in a.parents:
        if anc.name in ('tr', 'li', 'dd', 'p', 'td', 'dl', 'div'):
            t = ' '.join(anc.get_text(' ').split())
            if len(t) >= 6 and t != lab and not GENERIC.match(t):
                return t[:150]
            prev = anc.find_previous_sibling()
            if prev is not None:
                pt = ' '.join(prev.get_text(' ').split())
                if len(pt) >= 6:
                    return (pt + ' ' + lab)[:150]
    h = a.find_previous(['h1', 'h2', 'h3', 'h4', 'h5', 'dt', 'th', 'strong'])
    return ((' '.join(h.get_text(' ').split()) + ' ' + lab) if h else lab)[:150]

def extract(url, text):
    soup = BeautifulSoup(text, 'html.parser')
    for t in soup(['script', 'style']):
        t.decompose()
    res = {}
    for a in soup.find_all('a', href=True):
        href = a['href'].strip()
        if SKIP.search(href):
            continue
        full = urllib.parse.urljoin(url, href).split('#')[0]
        if not full.startswith('http') or full.rstrip('/') == url.rstrip('/'):
            continue
        is_pdf = full.lower().split('?')[0].endswith('.pdf')
        in_nav = a.find_parent(['nav', 'header', 'footer']) is not None
        if in_nav and not is_pdf:
            continue
        label = label_for(a)
        if SKIP.search(label) and not is_pdf:
            continue
        if not (is_pdf or KEY.search(label)):
            continue
        if len(label) < 2:
            label = os.path.basename(urllib.parse.unquote(full.split('?')[0]))
        res.setdefault(full, label[:200])
    return res

def rss(title, link, items):
    now = format_datetime(datetime.now(timezone.utc))
    out = ['<?xml version="1.0" encoding="UTF-8"?>','<rss version="2.0"><channel>',
           f'<title>{html.escape(title)}</title>', f'<link>{html.escape(link)}</link>',
           f'<description>{html.escape(title)} のガイドライン掲載ページに追加されたリンク</description>',
           f'<lastBuildDate>{now}</lastBuildDate>']
    for it in items:
        out += ['<item>', f'<title>{html.escape(it["title"])}</title>', f'<link>{html.escape(it["url"])}</link>',
                f'<guid isPermaLink="false">{hashlib.sha1(it["url"].encode()).hexdigest()}</guid>',
                f'<pubDate>{it["date"]}</pubDate>',
                f'<description>{html.escape(it["site"])}：{html.escape(it["page"])} に掲載</description>', '</item>']
    out.append('</channel></rss>')
    return '\n'.join(out)

def main():
    os.makedirs(STATE, exist_ok=True); os.makedirs(OUT, exist_ok=True)
    sites = json.load(open(os.path.join(ROOT, 'sites.json'), encoding='utf-8'))
    all_items = []; report = []
    for s in sites:
        sp = os.path.join(STATE, s['id'] + '.json')
        st = json.load(open(sp, encoding='utf-8')) if os.path.exists(sp) else {'seen': {}, 'items': []}
        first = not st['seen']; new = 0
        for page in s['pages']:
            try:
                links = extract(page, fetch(page))
            except Exception as e:
                report.append(f"NG {s['name']} {page} {e}"); continue
            for u, label in links.items():
                if u in st['seen']: continue
                st['seen'][u] = label
                if not first:
                    st['items'].insert(0, {'title': f"【{s['name']}】{label}", 'url': u, 'site': s['name'], 'page': page,
                                           'date': format_datetime(datetime.now(timezone.utc))}); new += 1
            time.sleep(2)
        st['items'] = st['items'][:MAX_ITEMS]
        json.dump(st, open(sp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        open(os.path.join(OUT, s['id'] + '.xml'), 'w', encoding='utf-8').write(rss(s['name'], s['pages'][0], st['items']))
        all_items += st['items']
        report.append(f"OK {s['name']} 既知{len(st['seen'])}件 新規{new}件" + ('（初回登録）' if first else ''))
    all_items.sort(key=lambda x: datetime.strptime(x['date'], '%a, %d %b %Y %H:%M:%S %z'), reverse=True)
    open(os.path.join(OUT, 'all.xml'), 'w', encoding='utf-8').write(rss('小児科関連学会 ガイドライン更新（まとめ）', 'https://github.com', all_items[:MAX_ITEMS]))
    print('\n'.join(report))

if __name__ == '__main__':
    main()
