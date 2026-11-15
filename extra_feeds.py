#!/usr/bin/env python3
# 公式フィードがないサイトの「新着」を RSS にする（ガイドライン監視とは別枠）
import json, os, re, hashlib, datetime, urllib.request, urllib.parse
from email.utils import format_datetime
from xml.sax.saxutils import escape
from bs4 import BeautifulSoup

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15'
MAX_ITEMS = 60
BASE = 'https://tishida9216-design.github.io/pediatric-guideline-feeds/'
NOW = datetime.datetime.now(datetime.timezone.utc)


def get(url, data=None):
    req = urllib.request.Request(url, data=data, headers={'User-Agent': UA, 'Accept-Language': 'ja'})
    with urllib.request.urlopen(req, timeout=90) as r:
        raw = r.read()
        cs = r.headers.get_content_charset() or 'utf-8'
    return raw.decode(cs, errors='replace')


def links_from(url, keep):
    soup = BeautifulSoup(get(url), 'html.parser')
    root = soup.find('main') or soup
    best = {}
    for a in root.find_all('a', href=True):
        u = urllib.parse.urljoin(url, a['href']).split('#')[0]
        if not keep(u):
            continue
        t = ' '.join(a.get_text(' ').split())
        if t in ('PR', ''):
            t = best.get(u, '')
        if len(t) > len(best.get(u, '')):
            best[u] = t
        best.setdefault(u, '')
    return [(u, t or u, None) for u, t in best.items()]


def tenmtv():
    return links_from('https://10mtv.jp/pc/content/search_list.php',
                      lambda u: re.search(r'10mtv\.jp/pc/content/detail\.php\?movie_id=\d+$', u))


def uomo_keep(u):
    p = urllib.parse.urlparse(u)
    if p.netloc != 'www.webuomo.jp' or p.query:
        return False
    s = [x for x in p.path.split('/') if x]
    if not s or s[0] in ('whatsnew', 'my-page', 'tag', 'search', 'magazine', 'information'):
        return False
    if s[0] == 'uomolist':
        return len(s) == 2
    return len(s) >= 3


def uomo():
    return links_from('https://www.webuomo.jp/whatsnew/', uomo_keep)


def minds():
    page = get('https://minds.jcqhc.or.jp/search/')
    nonce = re.search(r"AJAX_NONCE\s*=\s*'([0-9a-f]+)'", page).group(1)
    form = [('action', 'ajax_demo_action'), ('nonce', nonce),
            ('searchParams[category][category_c][]', 'child'),
            ('searchParams[release_day]', '1'), ('searchParams[show_latest]', 'true'),
            ('searchParams[show_count]', '30'), ('searchParams[sort_type]', '1'),
            ('searchParams[text]', ''), ('currentPage', '1'), ('dataType', 'json')]
    body = urllib.parse.urlencode(form).encode()
    j = json.loads(get('https://minds.jcqhc.or.jp/common/wp-admin/admin-ajax.php', body))
    out = []
    for p in j['posts'].values() if isinstance(j['posts'], dict) else j['posts']:
        sup = '・'.join(x for x in p.get('pdf_supervision', []) if x)
        title = p['title'] + (f'（{sup}）' if sup else '')
        d = None
        try:
            d = datetime.datetime.strptime(p.get('published_at', ''), '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            pass
        out.append((p['link'], title, d))
    return out


SITES = [
    ('10mtv', 'テンミニッツ・アカデミー 新着講義', 'https://10mtv.jp/pc/content/search_list.php', tenmtv),
    ('webuomo', 'UOMO 新着記事', 'https://www.webuomo.jp/whatsnew/', uomo),
    ('minds-child', 'Minds 小児ガイドライン新着', 'https://minds.jcqhc.or.jp/search/?小児=on&text=', minds),
]


def rss(fid, title, home, items):
    x = ['<?xml version="1.0" encoding="UTF-8"?>', '<rss version="2.0"><channel>',
         f'<title>{escape(title)}</title>', f'<link>{escape(home)}</link>',
         f'<description>{escape(title)}</description>',
         f'<lastBuildDate>{format_datetime(NOW)}</lastBuildDate>']
    for it in items:
        x += ['<item>', f'<title>{escape(it["title"])}</title>', f'<link>{escape(it["link"])}</link>',
              f'<guid isPermaLink="false">{hashlib.sha1(it["link"].encode()).hexdigest()}</guid>',
              f'<pubDate>{it["date"]}</pubDate>', '</item>']
    x.append('</channel></rss>')
    with open(f'docs/{fid}.xml', 'w', encoding='utf-8') as f:
        f.write('\n'.join(x))


def main():
    os.makedirs('docs', exist_ok=True)
    os.makedirs('state', exist_ok=True)
    for fid, title, home, fn in SITES:
        sp = f'state/{fid}.json'
        st = json.load(open(sp, encoding='utf-8')) if os.path.exists(sp) else {}
        seen = set(st.get('seen', []))
        items = st.get('items', [])
        try:
            found = fn()
        except Exception as e:
            print(f'[{fid}] ERROR {e}')
            found = None
        if found is not None:
            first = not st.get('init')
            fresh = []
            for link, t, d in found:
                if link in seen:
                    continue
                seen.add(link)
                fresh.append({'title': t, 'link': link, 'date': format_datetime(d or NOW)})
            items = fresh + items
            new = len(fresh)
            if found:
                st['init'] = True
            print(f'[{fid}] found={len(found)} new={new} first={first}')
        st['seen'] = sorted(seen)
        st['items'] = items[:MAX_ITEMS]
        json.dump(st, open(sp, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
        rss(fid, title, home, st['items'])


if __name__ == '__main__':
    main()
