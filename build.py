"""microCMS の中身から site/ にホームページ一式を書き出す。

使い方:
  python3 -I build.py            # 試作（検索エンジンに載せない noindex 付き）
  python3 -I build.py --release  # 本番（noindex を外し、正式アドレスで canonical・sitemap を出す）
  --source=cms / --source=local  # 読み先を決める（既定は、microCMS の設定があれば microCMS）
  --offline                      # 画像・PDFを取りに行かない（手元の確認用。写した画像・PDFの片づけもしない）
  --no-prune                     # microCMS から読んでも、使われていない写した画像・PDFを消さない

中身（文言・写真・ページ・メニュー・トップの部品・法人の情報）は、すべて cms.py が microCMS から読む。
このファイルが決めるのは見た目の形だけ。職員が管理画面で変えた分は、作り直すたびにそのまま反映される。
"""
import datetime
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I で起動しても同じフォルダの cms.py を読む
import cms  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(ROOT, "site")
BASE_URL = "https://www.inami-shakyo.or.jp/"
RELEASE = "--release" in sys.argv
# 見出しカード（LINEなどで送ったときの絵と題）や、印刷したときのアドレスに使う、このサイトの正式な場所
PUBLIC_URL = BASE_URL if RELEASE else os.environ.get("PREVIEW_URL", "https://inami-shakyo.github.io/hp-preview/")
SOURCE = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--source=")), "auto")
OFFLINE = "--offline" in sys.argv
MANIFEST = os.path.join(SITE, ".built.json")  # 前回書き出したページの一覧（消されたページを片づけるため）

GROUPS = ("社協について", "各種活動について", "ご案内")  # 横のメニューに出すまとまり（この順）
COLORS = {"緑": "green", "オレンジ": "orange", "青": "blue", "赤": "rose"}
ICONS = {
    "手をつなぐ": '<path d="M7 11.5 4 14.5a2 2 0 0 0 0 2.8l2.7 2.7a2 2 0 0 0 2.8 0l1-1"/><path d="m17 11.5 3 3a2 2 0 0 1 0 2.8l-2.7 2.7a2 2 0 0 1-2.8 0L9 14.5a1.8 1.8 0 0 1 2.5-2.5l1 1"/><path d="M12 3v3M6.5 5l1.5 2.5M17.5 5 16 7.5"/>',
    "人": '<circle cx="8" cy="7" r="3"/><circle cx="16.5" cy="8.5" r="2.5"/><path d="M2.5 20c0-3.3 2.5-6 5.5-6s5.5 2.7 5.5 6"/><path d="M13.5 15.2c.9-.8 1.9-1.2 3-1.2 2.6 0 4.5 2.2 4.5 5"/>',
    "吹き出し": '<path d="M4 5h11a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H9l-4 3.5V15H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z"/><path d="M19 9h1a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-1v2.5L16 18h-3"/>',
    "ハート": '<path d="M12 20s-7.5-4.6-7.5-10A4.3 4.3 0 0 1 12 7.3 4.3 4.3 0 0 1 19.5 10c0 5.4-7.5 10-7.5 10z"/>',
}
D = {}  # 読み込んだ中身（main で入れる）


# ブラウザに「このページが読み込んでよい場所」を伝える（Content-Security-Policy）。
# スクリプト・書体・画像はすべて自分のサイトの中から。外へは Googleフォームの埋め込みと送信だけを許す。
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; "
       "connect-src 'self'; frame-src https://docs.google.com https://www.google.com; "
       "form-action 'self' https://docs.google.com; base-uri 'self'; object-src 'none'")


def csp_meta():
    extra = "; upgrade-insecure-requests" if RELEASE else ""  # 手元の確認（http）では付けない
    return f'<meta http-equiv="Content-Security-Policy" content="{CSP}{extra}">\n'


def ver(rel):
    """見た目のファイルが変わったら、見る人のブラウザに古いものが残らないよう番号を付ける。"""
    import hashlib
    path = os.path.join(SITE, rel)
    return rel + "?v=" + hashlib.sha1(open(path, "rb").read()).hexdigest()[:8] if os.path.exists(path) else rel


def esc(s):
    return html.escape(s or "", quote=True)


def S(key, default=""):
    """法人の基本情報（settings）を読む。"""
    s = D["settings"][0] if D.get("settings") else {}
    return s.get(key) or default


def org():
    return S("orgName", "社会福祉法人 稲美町社会福祉協議会")


def icon(name):
    if name not in ICONS:
        return ""
    return ('<svg class="ico" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')


def is_out(url):
    return url.startswith("http")


def link_attrs(url):
    """外のサイトとファイル（PDFなど）は別のタブで開く。"""
    return ' target="_blank" rel="noopener"' if is_out(url) or cms.is_file(url) else ""


def menu(place):
    return [m for m in D["menu"] if m["place"] == place and m["label"] and m["url"]]


def text_of(h):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h or "")).strip()


# ---- 電話番号を途中で折り返さない ----
D_ = "[0-9０-９]"
PHONE = re.compile(
    r"(?<![0-9０-９])"
    r"(?:(?:TEL|FAX|ＴＥＬ|ＦＡＸ|Tel|Fax|☎|℡)\s*[:：]?\s*)?"               # 「TEL」「FAX」などの札も番号と一緒に
    rf"(?:[（(]\s*[0０]{D_}{{1,4}}\s*[）)]\s*|[0０]{D_}{{1,4}}\s*[-－‐ー]\s*)"    # 市外局番（079）や 079-
    rf"{D_}{{1,4}}\s*[-－‐ー]\s*{D_}{{3,4}}"
    r"(?![0-9０-９])")


def keep_phones(h):
    """本文の文字の中にある電話・FAX番号を、途中で折り返さないまとまりにする（タグの中は触らない）。"""
    parts = re.split(r"(<[^>]+>)", h or "")
    for i in range(0, len(parts), 2):
        parts[i] = PHONE.sub(lambda m: f'<span class="nw">{m.group(0)}</span>', parts[i])
    return "".join(parts)


# ---- 共通の枠 ----
def ogp(file, title, desc, image=None, article=False):
    """LINE・Facebook などにアドレスを貼ったときに出る見出しカード（OGP）。"""
    url = PUBLIC_URL + ("" if file == "index.html" else file)
    img = PUBLIC_URL + (image or "img/ogp.jpg")
    tags = [("og:site_name", org()), ("og:title", title), ("og:description", desc), ("og:url", url),
            ("og:type", "article" if article else "website"), ("og:image", img), ("og:locale", "ja_JP")]
    out = "".join(f'<meta property="{k}" content="{esc(v)}">\n' for k, v in tags)
    if not image:
        out += '<meta property="og:image:width" content="1200">\n<meta property="og:image:height" content="630">\n'
    return out + '<meta name="twitter:card" content="summary_large_image">\n'


def first_image(body):
    """本文の最初の写真（サイトの中に写したもの）。見出しカードの絵に使う。"""
    m = re.search(r'<img[^>]*\ssrc="(img/cms/[^"]+)"', body or "")
    return m.group(1) if m else None


def layout(file, title, main, desc="", crumbs=None, wide=False, image=None, article=False, noindex=False):
    head_robots = "" if RELEASE and not noindex else '<meta name="robots" content="noindex, nofollow">\n'
    canonical = f'<link rel="canonical" href="{BASE_URL}{"" if file == "index.html" else file}">\n' if RELEASE else ""
    full_title = org() if file == "index.html" else f"{title}｜{org()}"
    desc = (desc or S("description"))[:120]
    bc = ""
    if crumbs:
        parts = ['<li><a href="./">ホーム</a></li>']
        for t, h in crumbs[:-1]:
            parts.append(f'<li><a href="{h}">{esc(t)}</a></li>' if h else f"<li>{esc(t)}</li>")
        parts.append(f'<li aria-current="page">{esc(crumbs[-1][0])}</li>')
        bc = f'<nav class="crumbs" aria-label="現在の位置"><ol>{"".join(parts)}</ol></nav>'
    preview = "" if RELEASE else (
        '<div class="preview-bar" role="note">これは新しいホームページの試作です。'
        '内容は現在の公式ホームページから写したもので、まだ公開していません。</div>')
    alert = f'<div class="alert-bar" role="alert">{esc(S("alert")).replace(chr(10), "<br>")}</div>' if S("alert") else ""
    nav = "\n".join(f'<li><a href="{esc(m["url"])}"{link_attrs(m["url"])}'
                    f'{" aria-current=\"page\"" if m["url"] == file or (file == "index.html" and m["url"] == "./") else ""}>'
                    f'{esc(m["label"])}</a></li>' for m in menu("上のメニュー"))
    tel = S("tel")
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(full_title)}</title>
<meta name="description" content="{esc(desc)}">
{head_robots}{canonical}{ogp(file, title if file != "index.html" else org(), desc, image, article)}<link rel="icon" href="img/favicon.png">
{csp_meta()}<link rel="stylesheet" href="{ver("fonts/fonts.css")}">
<link rel="stylesheet" href="{ver("css/style.css")}">
<script src="{ver("js/early.js")}"></script>
</head>
<body>
<a class="skip" href="#main">本文へ移動</a>
{preview}{alert}
<header class="site-header">
 <div class="wrap header-in">
  <a class="brand" href="./"><img src="img/old/common_logo.png" alt="{esc(org())}" width="250" height="44"></a>
  <form class="hsearch" action="search.html" method="get" role="search">
   <input type="search" name="q" placeholder="サイト内を探す" aria-label="サイト内を探す" maxlength="40">
   <button type="submit">探す</button>
  </form>
  <div class="header-tools">
   {f'<a class="tel" href="tel:{esc(tel)}"><span class="tel-label">お電話</span>{esc(tel)}</a>' if tel else ''}
   <button type="button" class="fs-toggle" aria-pressed="false">文字を大きく</button>
   <button type="button" class="menu-toggle" aria-expanded="false" aria-controls="gnav">メニュー</button>
  </div>
 </div>
 <nav id="gnav" class="gnav" aria-label="メインメニュー"><ul class="wrap">{nav}</ul></nav>
</header>
<div class="wrap">{bc}</div>
<div class="wrap page{' page-wide' if wide else ''}">
 <main id="main" tabindex="-1">
{keep_phones(main)}
<p class="print-url">このページのアドレス：{esc(PUBLIC_URL + ("" if file == "index.html" else file))}</p>
 </main>
{'' if wide else side_html(file)}
</div>
{keep_phones(footer_html())}
<script src="{ver("js/main.js")}"></script>
</body>
</html>
"""


def side_html(file):
    blocks = []
    for g in GROUPS:
        items = [p for p in D["pages"] if p["group"] == g]
        if not items:
            continue
        lis = "".join(f'<li><a href="{p["file"]}"{" aria-current=\"page\"" if p["file"] == file else ""}>{esc(p["title"])}</a></li>'
                      for p in items)
        blocks.append(f'<section class="side-block"><h2>{esc(g)}</h2><ul>{lis}</ul></section>')
    return '<aside class="side" aria-label="サブメニュー">' + "".join(blocks) + "</aside>"


def footer_html():
    links = "".join(f'<li><a href="{esc(m["url"])}"{link_attrs(m["url"])}>{esc(m["label"])}</a></li>' for m in menu("下のリンク"))
    sns = "".join(f'<li><a href="{esc(m["url"])}" target="_blank" rel="noopener">{esc(m["label"])}</a></li>' for m in menu("SNS"))
    contact = []
    if S("tel") or S("fax"):
        contact.append(" ".join(x for x in [f'電話 <a href="tel:{esc(S("tel"))}">{esc(S("tel"))}</a>' if S("tel") else "",
                                            f'FAX {esc(S("fax"))}' if S("fax") else ""] if x))
    if S("mail"):
        contact.append(f'メール <a href="mailto:{esc(S("mail"))}">{esc(S("mail"))}</a>')
    return f"""<footer class="site-footer">
 <div class="wrap foot-in">
  <div class="foot-org">
   <p class="foot-name">{esc(org())}</p>
   <p>{esc(S("address"))}</p>
   <p>{"<br>".join(contact)}</p>
   <p>{esc(S("hours"))}</p>
  </div>
  <div class="foot-links">
   <ul>{links}</ul>
   <ul class="sns">{sns}</ul>
  </div>
 </div>
 <p class="copy">© {esc(org())}</p>
</footer>"""


# ---- お知らせ ----
def cat_key(c):
    return {"ニュース": "news", "募集": "recruit", "災害支援": "disaster"}.get(c, "news")


def iso_ja(iso):
    y, m, d = iso.split("-")
    return f"{int(y)}年{int(m)}月{int(d)}日"


def news_item(n):
    out = is_out(n["href"])  # 一覧から直接外へ出るか（本文のあるお知らせは自分のページへ）
    size = f' <span class="size">{esc(n["note"])}</span>' if n.get("note") else ""
    ext = ' <span class="ext">（外部サイト）</span>' if out and not n.get("note") else ""
    return (f'<li data-cat="{cat_key(n["category"])}" data-date="{n["iso"]}">'
            f'<time datetime="{n["iso"]}">{iso_ja(n["iso"])}</time>'
            f'<button type="button" class="cat cat-{cat_key(n["category"])}" data-filter="{cat_key(n["category"])}" title="「{esc(n["category"])}」だけを表示">{esc(n["category"])}</button>'
            f'<span class="news-title"><a href="{esc(n["href"])}"{link_attrs(n["href"])}>{esc(n["title"])}</a>{size}{ext}</span></li>')


def tabs(target):
    t = [("all", "すべて"), ("news", "ニュース"), ("recruit", "募集"), ("disaster", "災害支援")]
    b = "".join(f'<button type="button" role="tab" data-filter="{k}" aria-selected="{"true" if k == "all" else "false"}">{v}</button>'
                for k, v in t)
    return f'<div class="tabs" role="tablist" aria-label="お知らせの種類" data-target="{target}">{b}</div>'


def topic_page(n):
    meta = (f'<p class="meta"><time datetime="{n["iso"]}">{iso_ja(n["iso"])}</time>'
            f'<a class="cat cat-{cat_key(n["category"])}" href="topics_index.html?cat={cat_key(n["category"])}">{esc(n["category"])}</a></p>')
    extra = ""
    if n["link"]:
        note = f' <span class="size">{esc(n["note"])}</span>' if n["note"] else ""
        extra = f'<ul class="attach"><li><a href="{esc(n["link"])}"{link_attrs(n["link"])}>関連のファイル・ページを開く</a>{note}</li></ul>'
    main = (f'<article class="content">\n<h1>{esc(n["title"])}</h1>\n{meta}\n{maps_in(n["body"])}\n{form_buttons(n["body"])}{extra}\n</article>'
            '\n<p class="back"><a href="topics_index.html">お知らせの一覧へ戻る</a></p>')
    return layout(n["page"], n["title"], main, desc=text_of(n["body"]),
                  crumbs=[("お知らせ", "topics_index.html"), (n["title"], n["page"])],
                  image=first_image(n["body"]), article=True)


def topics_index():
    items = "\n".join(news_item(n) for n in D["news"])
    main = f"""<article class="content">
<h1>お知らせ</h1>
{tabs("all-news")}
<ul class="news-list" id="all-news">
{items}
</ul>
<p class="empty" hidden>この種類のお知らせは、いまはありません。</p>
</article>"""
    return layout("topics_index.html", "お知らせ", main, crumbs=[("お知らせ", "topics_index.html")])


# ---- 固定のページ ----
FORM_HEAD = "フォームでのお問い合わせ"


# ---- 地図（Googleマップ） ----
_map_cache = {}


def map_embed_url(q):
    """住所や施設名から、Googleマップの埋め込み用のアドレスを作る（APIキーは要らない）。
    書き出しのときに一度Googleに尋ねて、埋め込み専用の正式なアドレス（/maps/embed?…）に直しておく。"""
    from urllib.parse import quote
    if q in _map_cache:
        return _map_cache[q]
    url = f"https://www.google.com/maps?q={quote(q)}&output=embed&hl=ja&z=16"
    if not OFFLINE:
        import http.client
        try:
            c = http.client.HTTPSConnection("www.google.com", timeout=20, context=cms.SSL)
            c.request("GET", url[len("https://www.google.com"):], headers={"User-Agent": cms.UA})
            r = c.getresponse()
            loc = r.getheader("Location") or ""
            if r.status in (301, 302) and loc.startswith("https://www.google.com/maps/embed?"):
                url = loc
        except Exception as e:
            print(f"注意：地図のアドレスを確かめられませんでした（{q}：{e}）。そのままのアドレスで出します")
    _map_cache[q] = url
    return url


def maps_in(body):
    """本文に「［地図］施設名や住所」の行があれば、その場所の地図と「Googleマップで開く」ボタンに置きかえる。
    職員は管理画面でこの1行を書くだけでよい（段落の途中で改行して書いても見つける）。"""
    from urllib.parse import quote
    mark = re.compile(r"^\s*[［\[【]地図[］\]】]\s*(.+?)\s*$", re.S)

    def figure(q):
        open_url = "https://www.google.com/maps/search/?api=1&query=" + quote(q)
        return (f'<figure class="map"><iframe src="{esc(map_embed_url(q))}" title="地図：{esc(q)}" loading="lazy" '
                f'referrerpolicy="no-referrer-when-downgrade" allowfullscreen></iframe>'
                f'<figcaption><span class="map-q">地図：{esc(q)}</span>'
                f'<a class="map-open" href="{esc(open_url)}" target="_blank" rel="noopener">Googleマップで開く（道案内）</a>'
                f'</figcaption></figure>')

    def para(m):
        lines = re.split(r"<br\s*/?>", m.group(1))
        if not any(mark.match(re.sub(r"<[^>]+>", "", x)) for x in lines):
            return m.group(0)
        out, buf = [], []
        for x in lines:
            mm = mark.match(re.sub(r"<[^>]+>", "", x))
            q = re.sub(r"\s+", " ", html.unescape(mm.group(1))).strip() if mm else ""
            if mm and 0 < len(q) <= 80:
                if buf:
                    out.append("<p>" + "<br>".join(buf) + "</p>")
                    buf = []
                out.append(figure(q))
            else:
                buf.append(x)
        if buf and any(b.strip() for b in buf):
            out.append("<p>" + "<br>".join(buf) + "</p>")
        return "".join(out)
    return re.sub(r"<p>(.*?)</p>", para, body or "", flags=re.S)


FORM_LINK = re.compile(r'<a\s[^>]*href="(https://(?:docs\.google\.com/forms/|forms\.gle/)[^"]+)"[^>]*>(.*?)</a>', re.S)


def form_buttons(body):
    """本文にGoogleフォームへのリンクがあれば、ページの終わりに大きな「申し込む」ボタンを付ける。
    職員は本文にフォームのアドレスを貼るだけでよい（管理画面に専用の欄は作っていない）。"""
    seen, btns = set(), []
    for href, inner in FORM_LINK.findall(body or ""):
        href = html.unescape(href)
        if href in seen:
            continue
        seen.add(href)
        t = text_of(inner)
        vague = any(w in t for w in ("こちら", "ここ", "クリック")) or t in ("フォーム", "リンク", "申込", "申し込み")
        if t and not t.startswith("http") and 2 <= len(t) <= 24 and not vague:
            label = t  # 職員がリンクに付けた言葉（「参加の申し込み」など）をそのまま使う
        elif "アンケート" in text_of(body):
            label = "アンケートに答える"
        else:
            label = "申し込みフォームを開く"
        btns.append(f'<p class="form-open"><a href="{esc(href)}" target="_blank" rel="noopener">{esc(label)}</a></p>')
    if not btns:
        return ""
    return ('\n<div class="form-card form-apply">\n' + "\n".join(btns[:3]) +
            '\n<p class="form-note">Googleフォームが別の画面で開きます。Googleへのログインはいりません。</p>\n</div>\n')


def with_form(body, heads):
    """お問い合わせのページに、管理画面の「基本情報」で指定したGoogleフォームを開くボタンを入れる。
    本文に「フォームでのお問い合わせ」の見出しがあれば、その段（「準備中です」など）をボタンに置きかえる。
    フォームの欄を空にすれば、本文の段がそのまま出る。"""
    f = S("inquiryForm")
    if not f:
        return body, heads
    sid = "form"
    m = re.search(r'<h2 id="([^"]+)"[^>]*>\s*' + FORM_HEAD + r'\s*</h2>.*?(?=<h2|\Z)', body, re.S)
    if m:
        sid = m.group(1)
        body = body[:m.start()] + body[m.end():]
    else:
        heads = heads + [(sid, FORM_HEAD)]
    # 埋め込み（iframe）は、Googleにログインしたままのブラウザだと「ログインする必要があります」と出ることがあるため、
    # フォームは別の画面で開く形にしている（開いた画面ではログインなしで答えられる）
    block = (f'<h2 id="{esc(sid)}">{FORM_HEAD}</h2>\n'
             f'<div class="form-card">\n<p>下のボタンを押すと、お問い合わせのフォーム（Googleフォーム）が別の画面で開きます。'
             f'Googleへのログインはいりません。</p>\n'
             f'<p class="form-open"><a href="{esc(f["open"])}" target="_blank" rel="noopener">お問い合わせフォームを開く</a></p>\n'
             f'<p class="form-note">お急ぎのご用件は、お電話でどうぞ。</p>\n</div>\n')
    return body.rstrip() + "\n" + block, heads


def page_html(p):
    if p["slug"] == "inquiry":
        body, heads = with_form(p["body"], p["headings"])
    else:
        body, heads = maps_in(p["body"]) + form_buttons(p["body"]), p["headings"]
    toc = ""
    if len(heads) >= 3:
        lis = "".join(f'<li><a href="#{esc(i)}">{esc(t)}</a></li>' for i, t in heads)
        toc = f'<nav class="toc" aria-label="このページの内容"><ul>{lis}</ul></nav>'
    main = f'<article class="content">\n<h1>{esc(p["title"])}</h1>\n{toc}\n{body}\n</article>'
    crumbs = ([(p["group"], None)] if p["group"] in GROUPS else []) + [(p["title"], p["file"])]
    return layout(p["file"], p["title"], main, desc=p["lead"] or text_of(p["body"]), crumbs=crumbs,
                  image=first_image(p["body"]))


# ---- トップページ ----
ILLUST = {"手をつなぐ": "join", "人": "use", "吹き出し": "talk", "ハート": "care"}  # 目的カードの絵（管理画面で写真を入れればそちらを使う）
BREAK_AFTER = "、。をのには」"  # この字のあとで折り返してよい（「ない」は phrase() の中で別に扱う。「障がい」などを割らないよう、が・と・で等は入れない）


NO_LINE_START = "、。」』）を のにはがともでや"  # 行の頭に来ると読みにくい字（この字の前では折り返さない）


def phrase(text):
    """日本語を言葉の切れ目でだけ折り返す。切れ目ごとに区切った語のまとまりを、途中で割れない <span> で包む（.phrase と組で使う）。"""
    t = (text or "").replace("\n", "")
    chunks, cur, k = [], "", 0
    while k < len(t):
        step = 2 if t.startswith("ない", k) else 1
        cur += t[k:k + step]
        nxt = t[k + step:k + step + 1]
        if (step == 2 or t[k] in BREAK_AFTER) and nxt and nxt not in NO_LINE_START:
            chunks.append(cur)
            cur = ""
        k += step
    if cur:
        chunks.append(cur)
    return "".join(f'<span class="ph">{esc(c)}</span>' if len(c) <= 12 else esc(c) for c in chunks)


# トップのイラストの手前で、しゃぼん玉がいくつか、ふわふわ上っていく飾り（動きを減らす設定の人には出さない。見た目は style.css の .bubbles）
BUBBLES = ('<span class="bubbles" aria-hidden="true">'
           + "".join(f'<span class="bb b{i}"></span>' for i in range(1, 8)) + '</span>')


def home():
    parts = {k: [b for b in D["home"] if b["kind"] == k] for k in ("大きな写真", "目的カード", "ご案内", "関係機関")}
    pages = {p["file"]: p for p in D["pages"]}
    out = []

    hero = parts["大きな写真"][0] if parts["大きな写真"] else None
    title = hero["title"] if hero else org()
    # ひと言は、管理画面で入れた改行も「ここで折り返してよい」印として扱い、画面の幅に合わせて行の長さをそろえる
    lead = f'<p class="lead phrase">{phrase(hero["lead"])}</p>' if hero and hero["lead"] else ""
    art = ""
    if hero and hero["image"]:
        wh = f' width="{hero["width"]}" height="{hero["height"]}"' if hero["width"] else ""
        art = f'<div class="art"><img src="{esc(hero["image"])}" alt=""{wh}>{BUBBLES}</div>'
    out.append(f"""<section class="hero">
 <div class="wrap">
  <p class="label phrase">{phrase(org())}</p>
  <h1 class="phrase">{phrase(title)}</h1>
  {lead}
 </div>
 {art}
</section>""")

    if parts["目的カード"]:
        cards = []
        for b in parts["目的カード"]:
            target = pages.get(b["page"])
            img = b["image"] or f'img/illust/{ILLUST.get(b["icon"], "join")}.jpg'
            lis = "".join(f'<li class="phrase"><a href="{esc(b["page"])}#{esc(i)}">{phrase(t)}</a></li>' for i, t in (target["headings"] if target else []))
            href = esc(b["page"] or "#")
            cards.append(f"""<article class="card">
  <a class="pic" href="{href}" tabindex="-1" aria-hidden="true"><img src="{esc(img)}" alt="" loading="lazy"></a>
  <h3 class="phrase"><a href="{href}">{phrase(b["title"])}</a></h3>
  <p class="cl phrase">{phrase(b["lead"])}</p>
  <ul>{lis}</ul>
 </article>""")
        out.append(f'<section class="purposes" aria-labelledby="purpose-h"><div class="wrap"><h2 id="purpose-h" class="sec">目的からさがす</h2>'
                   f'<div class="cards">{"".join(cards)}</div></div></section>')

    items = "\n".join(news_item(n) for n in D["news"][:6])
    out.append(f"""<section class="newsarea" aria-labelledby="news-h">
 <div class="wrap">
  <div class="sechead"><h2 id="news-h" class="sec">お知らせ</h2><a class="more" href="topics_index.html">一覧を見る</a></div>
  {tabs("home-news")}
  <ul class="news-list" id="home-news">
{items}
  </ul>
  <p class="empty" hidden>この種類のお知らせは、いまはありません。</p>
 </div>
</section>""")

    if parts["ご案内"]:
        feats = []
        latest = next((n for n in D["news"] if "社協だより" in n["title"]), None)
        for b in parts["ご案内"]:
            main_btn = ""
            if b["title"] == "社協だより" and latest:  # 最新号のボタンは、お知らせから自動で作る
                main_btn = (f'<a class="issue" href="{esc(latest["href"])}"{link_attrs(latest["href"])}><span class="k">最新号</span>'
                            f'<span class="t">{esc(latest["title"].replace("掲載しました", ""))}</span><span class="s">{esc(latest["note"])}</span></a>')
            links = "".join(f'<a class="more" href="{esc(u)}"{link_attrs(u)}>{esc(t or "くわしく見る")}</a>' for t, u in b["links"])
            img = f'<img class="info-img" src="{esc(b["image"])}" alt="" loading="lazy">' if b["image"] else ""
            feats.append(f'<article class="info">{img}<h3 class="phrase">{phrase(b["title"])}</h3><p class="phrase">{phrase(b["lead"])}</p>{main_btn}<div class="il">{links}</div></article>')
        out.append(f'<section class="infos" aria-labelledby="info-h"><div class="wrap"><h2 id="info-h" class="sec">ご案内</h2>'
                   f'<div class="igrid">{"".join(feats)}</div></div></section>')

    if parts["関係機関"]:
        lis = "".join(f'<li><a href="{esc(b["links"][0][1] if b["links"] else "#")}" target="_blank" rel="noopener">'
                      f'<img src="{esc(b["image"])}" alt="{esc(b["title"])}" loading="lazy"></a></li>'
                      for b in parts["関係機関"] if b["image"])
        out.append(f'<section class="banners" aria-label="関係機関"><div class="wrap"><ul class="banner-list">{lis}</ul></div></section>')
    return layout("index.html", org(), "\n\n".join(out), wide=True)


# ---- 決まった形のページ ----
def router():
    """旧アドレス page1.html?id=○ を新しいページへ案内する。"""
    return """<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>ページを移動しました</title>
""" + csp_meta() + """<script src="js/router.js"></script></head>
<body><p>ページを移動しました。<a href="./">トップページへ</a></p></body></html>
"""


def not_found():
    main = """<article class="content wrap notfound">
<h1>ページが見つかりませんでした</h1>
<p>ホームページを新しくしたため、お探しのページの場所が変わったかもしれません。お手数ですが、上のメニューやトップページ、上の「サイト内を探す」からお探しください。</p>
<p><a href="./">トップページへ</a>　<a href="topics_index.html">お知らせの一覧へ</a></p>
</article>"""
    s = layout("404.html", "ページが見つかりませんでした", main, wide=True)
    # 旧サイトのアドレス（PHP・管理画面のPDF）で来た人を、新しい場所へ案内する
    fwd = '<script src="js/notfound.js"></script>\n'
    s = s.replace("</head>", fwd + "</head>", 1)
    # 404 はどの階層から開かれても崩れないよう、相対パスをサイトの根元からに直す
    return re.sub(r'(href|src|action)="(?!https?:|mailto:|tel:|#|/)([^"]*)"', r'\1="/\2"', s)


# ---- サイト内の検索 ----
def search_index():
    """検索に使う一覧（ページとお知らせの題・本文）。見る人のブラウザがこれを読んで探す（外のサービスは使わない）。"""
    rows = []
    for p in D["pages"]:
        rows.append({"t": p["title"], "u": p["file"], "x": text_of(p["body"])[:6000]})
    for n in D["news"]:
        rows.append({"t": n["title"], "u": n["href"], "d": n["iso"], "x": text_of(n["body"])[:3000], "o": 1 if is_out(n["href"]) or cms.is_file(n["href"]) else 0})
    return json.dumps(rows, ensure_ascii=False, separators=(",", ":"))


def search_page():
    main = """<article class="content">
<h1>サイト内を探す</h1>
<form class="search-form" action="search.html" method="get" role="search">
 <label for="q">探したい言葉</label>
 <div class="search-row"><input type="search" id="q" name="q" maxlength="40" placeholder="例：ボランティア　貸付　介護"><button type="submit">探す</button></div>
 <p class="search-hint">言葉を空白で区切ると、すべてを含むページを探します。PDFの中身は探せません。</p>
</form>
<p class="search-count" aria-live="polite"></p>
<ol class="search-results"></ol>
<noscript><p>この検索は、ブラウザの JavaScript を使います。上のメニューからお探しください。</p></noscript>
</article>"""
    s = layout("search.html", "サイト内を探す", main, noindex=True)
    s = re.sub(r'\s*<form class="hsearch".*?</form>', "", s, count=1, flags=re.S)  # このページでは頭の検索窓を出さない（二重になるため）
    return s.replace('<script src="' + ver("js/main.js") + '"></script>',
                     '<script src="' + ver("js/main.js") + '"></script>\n<script src="' + ver("js/search.js") + '"></script>', 1)


def sitemap(files):
    files = [f for f in files if f != "search.html"]
    urls = "".join(f"<url><loc>{BASE_URL}{'' if f == 'index.html' else f}</loc></url>" for f in files)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n'


def write(name, s):
    with open(os.path.join(SITE, name), "w", encoding="utf-8") as f:
        f.write(s)


def check_links(built):
    """管理画面で書かれたサイト内のつなぎ先に、無いページがないかを知らせる。"""
    have = set(built) | {"./", "topics_index.html", "page1.html", "404.html"}
    bad = []
    for m in D["menu"]:
        if not is_out(m["url"]) and not m["url"].startswith(("mailto:", "tel:", "#")) and m["url"].split("#")[0] not in have:
            bad.append(f'メニュー「{m["label"]}」→ {m["url"]}')
    for b in D["home"]:
        for t, u in b["links"] + ([("", b["page"])] if b["page"] else []):
            u = u.split("#")[0]
            if u and not is_out(u) and not u.startswith(("files/", "img/", "mailto:", "tel:")) and u not in have:
                bad.append(f'トップの「{b["title"]}」→ {u}')
    for x in bad:
        print("注意：つなぎ先のページがありません:", x)


# ---- 取り下げたファイルを公開物に残さない ----
CMS_DIRS = ("img/cms", "files/cms")                       # microCMS・Googleドライブから写したものの置き場（cms.py だけが書く）
CMS_REF = re.compile(r"(?:img|files)/cms/[A-Za-z0-9._-]+")


def prune_cms_assets():
    """写した画像・PDF（img/cms・files/cms）のうち、書き出したページが1つも指していないものを消す。
    cms.py は写し済みのファイルを取り直さず、自動公開も前回の分を引き継ぐので、そのままだと、管理画面で取り下げたり
    差し替えたりしたファイルが、アドレスを知る人には開けるまま公開物に残る。指されているかは、書き出したHTMLと
    search.json の中の文字から調べる（本文に手で書かれたアドレスも守る）。"""
    refs = set()
    for name in os.listdir(SITE):
        if name.endswith(".html") or name == "search.json":
            with open(os.path.join(SITE, name), encoding="utf-8", errors="ignore") as f:
                refs |= set(CMS_REF.findall(f.read()))
    removed = 0
    for d in CMS_DIRS:
        folder = os.path.join(SITE, d)
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            full = os.path.join(folder, name)
            if name.startswith(".") or f"{d}/{name}" in refs or os.path.islink(full) or not os.path.isfile(full):
                continue
            os.remove(full)
            removed += 1
            print(f"どのページからも使われていない写しを外しました: {d}/{name}")
    return removed


def main():
    global D
    D, where = cms.load_all(SITE, SOURCE, OFFLINE)
    built = ["index.html"]
    for p in D["pages"]:
        write(p["file"], page_html(p))
        built.append(p["file"])
    for n in D["news"]:
        if n["page"]:
            write(n["page"], topic_page(n))
            built.append(n["page"])
    write("index.html", home())
    write("topics_index.html", topics_index())
    write("page1.html", router())
    write("404.html", not_found())
    write("search.json", search_index())
    write("search.html", search_page())
    built += ["topics_index.html", "search.html"]
    # 管理画面で消された・公開を止めたページを片づける（前回このスクリプトが書き出したものだけが対象）
    before = json.load(open(MANIFEST)) if os.path.exists(MANIFEST) else []
    for f in set(before) - set(built):
        if re.fullmatch(r"[a-z0-9_-]+\.html", f) and os.path.exists(os.path.join(SITE, f)):
            os.remove(os.path.join(SITE, f))
            print("管理画面に無くなったページを外しました:", f)
    json.dump(sorted(built), open(MANIFEST, "w"))
    # 写した画像・PDFの片づけは、microCMSの5つの入れ物をすべて読めたときだけ行う（読み損ねで消しすぎないため）
    if OFFLINE or "--no-prune" in sys.argv:
        pass
    elif all(v == "microCMS" for v in where.values()) and D["pages"] and D["home"]:
        prune_cms_assets()
    else:
        print("注意：microCMS からすべては読めなかったので、写した画像・PDFの片づけはしませんでした")
    check_links(built)
    if RELEASE:
        write("sitemap.xml", sitemap(built))
        write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}sitemap.xml\n")
    else:
        write("robots.txt", "User-agent: *\nDisallow: /\n")
    print("読み先:", "、".join(f"{k}={v}" for k, v in where.items()))
    print(f"お知らせ {len(D['news'])} 件・ページ {len(D['pages'])} 件・トップの部品 {len(D['home'])} 件・メニュー {len(D['menu'])} 件")
    print(f"{len(built)} ページを書き出しました（{'本番' if RELEASE else '試作・検索除外'}）", datetime.date.today())


if __name__ == "__main__":
    main()
