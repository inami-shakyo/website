"""ホームページの中身を microCMS から読む部分（build.py から使う）。

microCMS の入れ物（API）は5つ。どれも「リスト形式」:
  news     … お知らせ
  pages    … 固定のページ（社協の概要・各事業所の案内など）
  home     … トップページの部品（大きな写真・目的カード・ご案内・関係機関）
  menu     … 上のメニュー・下のリンク・SNS
  settings … 法人の名前・住所・電話など（1件だけ入れる）

読み先は入れ物ごとに2つのどちらか:
  - microCMS（microcms/microcms.env にサービスIDとAPIキーがあるとき。環境変数 MICROCMS_SERVICE_ID / MICROCMS_API_KEY でも可）
  - 手元の content/cms_<入れ物>.json（microCMS と同じ形。cms_migrate.py が旧サイトから作る。未接続のときの見本）
microCMS にまだ入れ物が無いとき（404）は、その入れ物だけ手元の分を使う。

職員が microCMS に入れた写真と、Googleドライブの共有リンクのPDFは、書き出しのときにホームページ側へ写す。
（microCMS の無料プランは月20GBの転送量を超えると止まるため、見る人が microCMS から直接読まない形にしている）
"""
import datetime
import hashlib
import json
import os
import re
from urllib.error import HTTPError
from urllib.parse import urlparse, parse_qs, urlencode
from urllib.request import Request, urlopen

ROOT = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(ROOT, "content")
ENV = os.path.join(ROOT, "microcms", "microcms.env")
ENDPOINT = "news"
ENDPOINTS = ("news", "pages", "home", "menu", "settings")
ORDERS = {"news": "-date", "pages": "order", "home": "order", "menu": "order", "settings": "createdAt"}
JST = datetime.timezone(datetime.timedelta(hours=9))
UA = "inami-shakyo-site-build"
SLUG = re.compile(r"^[a-z0-9_-]{2,40}$")
RESERVED = re.compile(r"^(index|404|page1|topics_index|topics_\d+|news_.*)$")
OLD_PAGE = re.compile(r"[A-Za-z0-9_-]{1,40}")   # お知らせの旧ページ名・IDに使える字（ファイル名になるため）
MAX_DOWNLOAD = 100 * 1024 * 1024                # 1ファイルあたりの上限（100MB）


def _ssl_context():
    """https の証明書の確かめ方。Mac の python.org 版 Python は証明書を持っていないので、OS の証明書を使う。"""
    import ssl
    ctx = ssl.create_default_context()
    if not ctx.get_ca_certs():
        for path in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt"):
            if os.path.exists(path):
                ctx.load_verify_locations(path)
                break
    return ctx


SSL = _ssl_context()


def config():
    conf = {"service": os.environ.get("MICROCMS_SERVICE_ID", ""), "key": os.environ.get("MICROCMS_API_KEY", "")}
    if os.path.exists(ENV):
        for line in open(ENV, encoding="utf-8"):
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if k == "MICROCMS_SERVICE_ID" and not conf["service"]:
                    conf["service"] = v
                if k == "MICROCMS_API_KEY" and not conf["key"]:
                    conf["key"] = v
    return conf


def fetch_list(conf, endpoint):
    """microCMS の入れ物から公開中のものを全件取る（100件ずつ）。"""
    out, offset = [], 0
    base = os.environ.get("MICROCMS_BASE_URL") or f"https://{conf['service']}.microcms.io"  # 試験用に差し替え可
    while True:
        q = urlencode({"limit": 100, "offset": offset, "orders": ORDERS.get(endpoint, "createdAt")})
        req = Request(f"{base}/api/v1/{endpoint}?{q}", headers={"X-MICROCMS-API-KEY": conf["key"], "User-Agent": UA})
        with urlopen(req, timeout=30, context=SSL) as r:
            d = json.load(r)
        out += d["contents"]
        offset += len(d["contents"])
        if offset >= d["totalCount"] or not d["contents"]:
            return out


def fetch_cms(conf):
    return fetch_list(conf, "news")


def local(endpoint):
    path = os.path.join(CONTENT, f"cms_{endpoint}.json")
    return json.load(open(path, encoding="utf-8"))["contents"] if os.path.exists(path) else []


def jst_date(s):
    """microCMS の日時（UTC）を日本時間の日付 YYYY-MM-DD にする。"""
    t = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    return t.astimezone(JST).strftime("%Y-%m-%d")


def first(v, default=""):
    """セレクトの値（配列）を1つの文字列にする。"""
    if isinstance(v, list):
        return v[0] if v else default
    return v or default


def _download(url, dest_dir, site, name_hint):
    """url を site/dest_dir に保存し、サイト内の相対パスを返す。失敗したら None。"""
    os.makedirs(os.path.join(site, dest_dir), exist_ok=True)
    ext = os.path.splitext(urlparse(url).path)[1].lower()[:5]
    name = name_hint or hashlib.sha1(url.encode()).hexdigest()[:16] + ext
    rel = f"{dest_dir}/{name}"
    path = os.path.join(site, rel)
    root = os.path.realpath(site) + os.sep
    if not os.path.realpath(path).startswith(root):   # 保存先が site/ の外に出る名前は使わない
        return None
    if os.path.exists(path):
        return rel
    try:
        with urlopen(Request(url, headers={"User-Agent": UA}), timeout=60, context=SSL) as r:
            body = r.read(MAX_DOWNLOAD + 1)
    except Exception:
        return None
    if len(body) > MAX_DOWNLOAD:   # 想定より大きいものは写さない（実行環境の容量・時間を食われないように）
        return None
    if name.endswith(".pdf") and not body.startswith(b"%PDF"):
        return None  # Googleドライブが確認画面を返したとき（共有設定が違う・大きすぎる）
    open(path, "wb").write(body)
    return rel


def drive_id(url):
    """Googleドライブの共有リンクからファイルの番号を取る。英数字と - _ だけの番号以外は使わない（保存名に使うため）。"""
    p = urlparse(url)
    if (p.hostname or "").lower() != "drive.google.com":
        return None
    m = re.search(r"/file/d/([A-Za-z0-9_-]+)", p.path)
    did = m.group(1) if m else parse_qs(p.query).get("id", [None])[0]
    return did if did and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", did) else None


def localize_link(url, site, offline):
    """Googleドライブの共有リンクなら、PDFをサイトに写してその場所を返す。"""
    url = (url or "").strip()
    if not url or offline:
        return url
    did = drive_id(url)
    if did:
        rel = _download(f"https://drive.google.com/uc?export=download&id={did}", "files/cms", site, f"{did}.pdf")
        if rel:
            return rel
    return url


IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def is_microcms_image(url):
    """microCMSの画像置き場（https の microcms-assets.io か、その下の images. など）で、画像の拡張子のものだけ。
    アドレスの途中に文字が入っているだけのもの（https://悪い所/?microcms-assets.io など）は通さない。"""
    p = urlparse(url)
    host = (p.hostname or "").lower()
    if p.scheme != "https" or p.username or p.password or p.port not in (None, 443):
        return False
    if host != "microcms-assets.io" and not host.endswith(".microcms-assets.io"):
        return False
    return os.path.splitext(p.path)[1].lower() in IMAGE_EXT


def localize_image(url, site, offline):
    if not url or offline or not is_microcms_image(url):
        return url or ""
    return _download(url.split("?")[0], "img/cms", site, None) or url


def site_link(url):
    """管理画面に書かれたつなぎ先を、サイトの中で使える形にする。"""
    url = (url or "").strip()
    url = re.sub(r"^https?://(www\.)?inami-shakyo\.or\.jp/", "", url)
    if url in ("", "/", "index.html"):
        return "./" if url else ""
    if re.fullmatch(r"[a-z0-9_-]{2,40}", url):
        return url + ".html"  # 「page1_4」とだけ書かれたとき
    if safe_url(url) is None:   # javascript: data: など、http・https・mailto・tel 以外の書き方は出さない
        print(f"注意：使えないつなぎ先を外しました：{url[:40]}")
        return ""
    return url


# 本文に残してよいタグと属性（これ以外はすべて外す。管理画面の乗っ取りや貼り付けの誤りで、危ないものが載らないように）
ALLOW_TAGS = {"h1", "h2", "h3", "h4", "h5", "p", "br", "hr", "strong", "b", "em", "i", "u", "s", "span", "a", "img",
              "ul", "ol", "li", "table", "thead", "tbody", "tr", "th", "td", "figure", "figcaption", "blockquote", "div"}
ALLOW_ATTRS = {"a": {"href", "target", "rel"}, "img": {"src", "alt", "width", "height"}, "th": {"colspan", "rowspan"},
               "td": {"colspan", "rowspan"}, "h1": {"id"}, "h2": {"id"}, "h3": {"id"}, "h4": {"id"}, "h5": {"id"}}
DROP_WITH_CONTENT = {"script", "style", "iframe", "object", "embed", "svg", "math", "form", "template", "noscript",
                     "textarea", "select", "button", "frame", "frameset", "audio", "video", "canvas", "head", "title"}


def safe_url(u, img=False):
    u = (u or "").strip()
    low = re.sub(r"[\s\x00-\x1f]", "", u).lower()
    if low.startswith(("http://", "https://", "#", "/")) or (not img and low.startswith(("mailto:", "tel:"))):
        return u
    if re.match(r"^[a-z][a-z0-9+.-]*:", low):   # javascript: data: vbscript: など、上以外の書き方は使わせない
        return None
    return u                                   # サイト内の相対の場所


def sanitize(h):
    """許したタグと属性だけを残す。"""
    import html as _html
    from html.parser import HTMLParser

    class S(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.out, self.skip = [], 0

        def handle_starttag(self, tag, attrs, closed=False):
            if tag in DROP_WITH_CONTENT:
                if not closed:
                    self.skip += 1
                return
            if self.skip or tag not in ALLOW_TAGS:
                return
            keep = []
            for k, v in attrs:
                if k not in ALLOW_ATTRS.get(tag, set()):
                    continue
                if k in ("href", "src"):
                    v = safe_url(v, img=(k == "src"))
                    if v is None:
                        continue
                keep.append(f'{k}="{_html.escape(v or "", quote=True)}"')
            self.out.append("<" + tag + ("" if not keep else " " + " ".join(keep)) + (" />" if closed else ">"))

        def handle_startendtag(self, tag, attrs):
            self.handle_starttag(tag, attrs, closed=True)

        def handle_endtag(self, tag):
            if tag in DROP_WITH_CONTENT:
                self.skip = max(0, self.skip - 1)
                return
            if not self.skip and tag in ALLOW_TAGS and tag not in ("br", "hr", "img"):
                self.out.append(f"</{tag}>")

        def handle_data(self, d):
            if not self.skip:
                self.out.append(_html.escape(d, quote=False))

        def handle_entityref(self, name):
            if not self.skip:
                self.out.append(f"&{name};")

        def handle_charref(self, name):
            if not self.skip:
                self.out.append(f"&#{name};")

    p = S()
    p.feed(h or "")
    p.close()
    return "".join(p.out)


FILE_RE = re.compile(r"\.(pdf|xlsx?|docx?|pptx?)([?#].*)?$", re.I)


def is_file(url):
    """PDF・Excel・Word などのファイルを指すリンクか（サイトの files/ 以下も含む）。"""
    u = (url or "").strip()
    return u.startswith("files/") or bool(FILE_RE.search(u))


def open_in_new_tab(h):
    """外のサイトとファイル（PDFなど）へのリンクは別のタブで開く。管理画面で target を付けた場合も rel を揃える。"""
    def f(m):
        tag = m.group(0)
        href = re.search(r'href=["\']([^"\']*)["\']', tag)
        url = href.group(1) if href else ""
        if "target=" not in tag and (url.startswith(("http://", "https://")) or is_file(url)):
            tag = tag[:2] + ' target="_blank"' + tag[2:]
        if 'target="_blank"' in tag and "rel=" not in tag:
            tag = tag[:2] + ' rel="noopener"' + tag[2:]
        return tag
    return re.sub(r"<a\s[^>]*>", f, h)


def fix_file_labels(h):
    """ファイルのリンクの後ろの「PDF・66KB」を、実際の種類に合わせる（旧サイトから移した本文では、Excel・Wordにも「PDF」と書いてある）。"""
    def f(m):
        return m.group(1) + ("Excel" if m.group(2).lower().startswith("xls") else "Word") + m.group(3)
    return re.sub(r'(<a\s[^>]*href=["\'][^"\']*\.(xlsx?|docx?)(?:[?#][^"\']*)?["\'][^>]*>(?:(?!</a>).)*</a>(?:\s|&nbsp;)*)PDF(・)',
                  f, h, flags=re.I | re.S)


def clean_body(h, site, offline):
    """職員が入れた本文を、ホームページに載せられる形に整える。"""
    h = sanitize(h)
    # 移行のとき正式アドレスで入れたサイト内リンクを、相対の場所に戻す
    h = re.sub(r"(href=[\"'])https?://(www\.)?inami-shakyo\.or\.jp/", r"\1", h)
    # 本文の中の Googleドライブのリンクも、PDFをサイトに写してから差し替える
    h = re.sub(r'(href=["\'])(https://drive\.google\.com/[^"\']+)(["\'])',
               lambda m: m.group(1) + localize_link(m.group(2), site, offline) + m.group(3), h)
    h = re.sub(r'(<img[^>]*?src=["\'])([^"\']+)(["\'])',
               lambda m: m.group(1) + localize_image(m.group(2), site, offline) + m.group(3), h)
    h = re.sub(r"<img(?![^>]*loading=)", '<img loading="lazy"', h)
    h = open_in_new_tab(h)
    h = fix_file_labels(h)
    # PDF・Excel へのリンクに印を付ける（見た目で「ファイルが開く」とわかるように）
    h = re.sub(r'<a (?![^>]*class=)([^>]*href=["\'][^"\']*\.(pdf|xlsx?|docx?)["\'])', r'<a class="file" \1', h, flags=re.I)
    h = re.sub(r'<a (?![^>]*class=)([^>]*href=["\']files/)', r'<a class="file" \1', h)
    h = re.sub(r"<table", '<div class="table-wrap"><table', h)
    h = re.sub(r"</table>", "</table></div>", h)
    return h.strip()


def add_heading_ids(h):
    """大見出しに id が無ければ付ける（目次とトップのカードから飛べるように）。"""
    n = [0]

    def f(m):
        if "id=" in m.group(1):
            return m.group(0)
        n[0] += 1
        return f'<h2 id="sec{n[0]}"{m.group(1)}>'
    return re.sub(r"<h2([^>]*)>", f, h)


def headings(h):
    return [(i, re.sub(r"<[^>]+>", "", t).strip())
            for i, t in re.findall(r'<h2[^>]*\sid=["\']([^"\']+)["\'][^>]*>(.*?)</h2>', h, re.S)]


def normalize_news(rec, site, offline=False):
    cat = first(rec.get("category"), "ニュース")
    iso = jst_date(rec.get("date") or rec.get("publishedAt") or rec["createdAt"])
    if not OLD_PAGE.fullmatch(str(rec.get("id") or "")):
        print(f"注意：お知らせのIDに使えない字があるので飛ばしました（{rec.get('title')}）")
        return None
    old = (rec.get("oldPage") or "").strip()
    if old and not OLD_PAGE.fullmatch(old):
        print(f"注意：お知らせの「旧ページ名」に使えない字があるので無視しました（{rec.get('title')}）")
        old = ""
    page = f"topics_{old}.html" if old else f"news_{rec['id']}.html"
    link = localize_link(rec.get("link"), site, offline)
    body = clean_body(rec.get("body") or "", site, offline)
    return {
        "id": rec["id"], "title": rec["title"].strip(), "category": cat, "iso": iso,
        "body": body, "page": page if body else None,
        "href": page if body else (site_link(link) or "#"), "link": site_link(link),
        "external": link.startswith("http"), "note": (rec.get("linkNote") or "").strip(),
    }


normalize = normalize_news  # 以前の呼び名


def normalize_page(rec, site, offline=False):
    slug = (rec.get("slug") or "").strip()
    if not SLUG.match(slug) or RESERVED.match(slug):
        print(f"注意：ページの名前「{slug}」は使えないので飛ばしました（{rec.get('title')}）")
        return None
    body = add_heading_ids(clean_body(rec.get("body") or "", site, offline))
    return {"slug": slug, "file": slug + ".html", "title": rec["title"].strip(),
            "group": first(rec.get("group"), "メニューに出さない"), "order": rec.get("order") or 0,
            "lead": (rec.get("lead") or "").strip(), "body": body, "headings": headings(body)}


def _size(v):
    """画像の幅・高さ。1〜20000 の整数だけ通す（属性にそのまま入るため）。"""
    return v if isinstance(v, int) and not isinstance(v, bool) and 0 < v <= 20000 else None


def normalize_home(rec, site, offline=False):
    img = rec.get("image") or {}
    w, h = (_size(img.get("width")), _size(img.get("height"))) if isinstance(img, dict) else (None, None)
    if not (w and h):
        w = h = None   # 片方だけ使えないときは、両方出さない
    return {"kind": first(rec.get("kind")), "order": rec.get("order") or 0, "title": (rec.get("title") or "").strip(),
            "lead": (rec.get("lead") or "").strip(),
            "image": localize_image(img.get("url") if isinstance(img, dict) else img, site, offline),
            "width": w,
            "height": h,
            "page": site_link(rec.get("page")), "color": first(rec.get("color"), "緑"), "icon": first(rec.get("icon"), "なし"),
            "links": [(rec.get(f"linkLabel{s}") or "", site_link(localize_link(rec.get(f"linkUrl{s}"), site, offline)))
                      for s in ("", "2") if rec.get(f"linkUrl{s}")]}


def normalize_menu(rec, site, offline=False):
    return {"place": first(rec.get("place")), "order": rec.get("order") or 0,
            "label": (rec.get("label") or "").strip(), "url": site_link(rec.get("url"))}


FORM_ID = re.compile(r"^https://docs\.google\.com/forms/d/e/([A-Za-z0-9_-]{20,120})/(viewform|formResponse|closedform)\b")


def google_form(raw, offline=False):
    """管理画面に貼られたGoogleフォームのアドレスから、埋め込み用と別画面用のアドレスを作る。
    貼ってよいのは「送信」の画面のリンク（docs.google.com/forms/d/e/…/viewform）、短いリンク（forms.gle/…）、
    埋め込み用のHTML（<iframe src=…>）のどれか。それ以外は表示しない。"""
    raw = (raw or "").strip()
    if not raw:
        return None
    height = 1500
    if "<iframe" in raw:
        m = re.search(r'src="([^"]+)"', raw)
        h = re.search(r'height="(\d{3,4})"', raw)
        if h and 400 <= int(h.group(1)) <= 6000:
            height = int(h.group(1))
        raw = m.group(1) if m else ""
    raw = raw.replace("&amp;", "&")
    if re.match(r"^https://forms\.gle/[A-Za-z0-9]{6,40}$", raw):
        if offline:
            return None
        try:  # 短いリンクは、行き先（docs.google.com の正式なアドレス）に直して使う
            with urlopen(Request(raw, headers={"User-Agent": UA}), timeout=30, context=SSL) as r:
                raw = r.geturl()
        except Exception as e:
            print(f"注意：お問い合わせフォームの短いリンクを開けませんでした（{e}）。今回はフォームを出しません")
            return None
    m = FORM_ID.match(raw)
    if not m:
        if re.match(r"^https://docs\.google\.com/forms/d/[A-Za-z0-9_-]+/edit", raw):
            print("注意：お問い合わせフォームのアドレスが「編集用」です。フォームの「送信」→リンクのアドレスを貼ってください。今回はフォームを出しません")
        else:
            print("注意：お問い合わせフォームのアドレスがGoogleフォームのものではないので、フォームを出しません")
        return None
    if m.group(2) == "closedform":
        print("注意：お問い合わせフォームが「回答を受け付けていません」になっています（Googleフォームの「回答」タブで切り替えます）")
    base = f"https://docs.google.com/forms/d/e/{m.group(1)}/viewform"
    return {"embed": base + "?embedded=true", "open": base, "height": height}


def normalize_settings(rec, site, offline=False):
    out = {k: (rec.get(k) or "").strip() for k in ("orgName", "address", "tel", "fax", "mail", "hours", "description", "alert")}
    out["inquiryForm"] = google_form(rec.get("inquiryForm"), offline)
    return out


NORMALIZE = {"news": normalize_news, "pages": normalize_page, "home": normalize_home,
             "menu": normalize_menu, "settings": normalize_settings}


def load_all(site, source="auto", offline=False):
    """5つの入れ物を読んで、そろえた形で返す。"""
    conf = config()
    use_cms = source == "cms" or (source == "auto" and conf["service"] and conf["key"])
    if use_cms and not (conf["service"] and conf["key"]):
        raise SystemExit("microCMS のサービスIDとAPIキーが見つかりません（microcms/microcms.env）")
    data, where = {}, {}
    for ep in ENDPOINTS:
        raw = None
        if use_cms:
            try:
                raw, where[ep] = fetch_list(conf, ep), "microCMS"
            except HTTPError as e:
                if e.code != 404:
                    raise
                print(f"注意：microCMS に「{ep}」の入れ物がまだ無いので、手元の content/cms_{ep}.json を使いました")
        if raw is None:
            raw, where[ep] = local(ep), "手元"
        items = [x for x in (NORMALIZE[ep](r, site, offline) for r in raw) if x]
        if ep == "news":
            items.sort(key=lambda n: (n["iso"], n["id"]), reverse=True)
        elif ep != "settings":
            items.sort(key=lambda n: n["order"])
        data[ep] = items
    return data, where


def load(site, source="auto", offline=False):
    """お知らせだけを読む（以前の呼び方）。"""
    data, where = load_all(site, source, offline)
    return data["news"], where["news"]
