#!/usr/bin/env python3
"""taxes.gov.az → data/taxes.json

GitHub Actions bu skripti hər saat işə salır (bax: .github/workflows/taxes-sync.yml).
Rəsmi səhifədən oxunur:
  • qeyri-rezidentlərin reyestri (şirkət, ölkə, qeydiyyat tarixi);
  • "Tez-tez verilən suallar" (hər sual rəsmi mətndə dəyişibsə, saytda rəsmi mətn göstərilir);
  • əsas rəqəmlər: dövriyyə həddi, ƏDV dərəcəsi, məcburi uçot tarixi, müddətlər, valyutalar, e-poçt, linklər.
Sayt (index.html) data/taxes.json faylını oxuyub öz məlumatının üzərinə tətbiq edir.

Yalnız Python standart kitabxanası istifadə olunur. Yerli sınaq üçün:
    python3 scripts/taxes_sync.py --lang az --file saxlanmis-sehife.html
"""
import argparse, datetime, difflib, hashlib, json, os, re, sys, time, urllib.parse, urllib.request
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_URL = "https://www.taxes.gov.az/"
CHANGE = os.path.join(ROOT, "change.md")
LANGS = {
    "az": {"title": "Azərbaycanca səhifə", "dir": "data",
           "url": "https://www.taxes.gov.az/az/page/reqemsal-iqtisadiyyat-uzre-vergitutma"},
}
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"

# ----------------------------------------------------------------- HTML ağacı
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
BLOCK = {"p", "div", "ul", "ol", "li", "table", "thead", "tbody", "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6",
         "details", "summary", "article", "section", "hr", "br", "blockquote", "pre"}
SKIP = {"script", "style", "svg", "noscript", "template"}


class Node:
    __slots__ = ("tag", "attrs", "kids", "parent")

    def __init__(self, tag, attrs=None, parent=None):
        self.tag, self.attrs, self.kids, self.parent = tag, dict(attrs or []), [], parent

    @property
    def cls(self):
        return set((self.attrs.get("class") or "").split())


class Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root")
        self.stack = [self.root]

    def _close(self, *tags):
        if self.stack[-1].tag in tags:
            self.stack.pop()

    def handle_starttag(self, tag, attrs):
        if tag in BLOCK and tag != "p":
            self._close("p")            # <p> blok elementdən əvvəl avtomatik bağlanır
        if tag == "p":
            self._close("p")
        if tag == "li":
            self._close("li")
        if tag in ("td", "th"):
            self._close("td", "th")
        if tag == "tr":
            self._close("td", "th"); self._close("tr")
        n = Node(tag, attrs, self.stack[-1])
        self.stack[-1].kids.append(n)
        if tag not in VOID:
            self.stack.append(n)

    def handle_startendtag(self, tag, attrs):
        n = Node(tag, attrs, self.stack[-1])
        self.stack[-1].kids.append(n)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].kids.append(data)


def build(src):
    b = Builder()
    b.feed(src)
    b.close()
    return b.root


def walk(n):
    for k in n.kids:
        if isinstance(k, Node):
            yield k
            if k.tag not in SKIP:
                yield from walk(k)


def find(n, tag=None, cls=None, id=None):
    return [k for k in walk(n) if (tag is None or k.tag == tag) and (cls is None or cls in k.cls)
            and (id is None or k.attrs.get("id") == id)]


def ws(s):
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def text(n):
    out = []

    def rec(x):
        for k in x.kids:
            if isinstance(k, str):
                out.append(k)
            elif k.tag not in SKIP:
                if k.tag == "br":
                    out.append(" ")
                rec(k)
    rec(n)
    return ws("".join(out))


def block_lines(n):
    """Səhifə mətni — hər blok ayrıca sətirdə (dəyişikliyi müqayisə etmək üçün)."""
    out = []

    def rec(x):
        for k in x.kids:
            if isinstance(k, str):
                out.append(re.sub(r"\s+", " ", k))     # mənbədəki sətir keçidləri yox, yalnız bloklar sətir yaradır
            elif k.tag not in SKIP:
                blk = k.tag in BLOCK and k.tag not in ("td", "th")    # cədvəl sətri bir sətirdə
                if blk:
                    out.append("\n")
                if k.tag in ("td", "th"):
                    out.append(" | ")
                rec(k)
                if blk:
                    out.append("\n")
    rec(n)
    return [l for l in (ws(x) for x in "".join(out).split("\n")) if l]


def absurl(href):
    href = (href or "").strip()
    if not href or href.startswith(("mailto:", "tel:", "#")):
        return href
    return urllib.parse.quote(urllib.parse.urljoin(BASE_URL, href), safe=":/?&=%#+,;@!$'()*~")


def inline_md(n):
    """HTML → saytın sadə markdown formatı: **qalın**, [mətn](link), sətir keçidi."""
    out = []

    def rec(x):
        for k in x.kids:
            if isinstance(k, str):
                out.append(re.sub(r"\s+", " ", k.replace("\xa0", " ")))
            elif k.tag in SKIP:
                continue
            elif k.tag == "br":
                out.append("\n")
            elif k.tag in ("strong", "b"):
                t = text(k)
                if t:
                    out.append(f"**{t}**")
            elif k.tag == "a":
                t, h = text(k), k.attrs.get("href", "")
                if h.startswith("mailto:") or not h:
                    out.append(t)
                else:
                    h = absurl(h)
                    out.append(h if ws(t).rstrip("/") in (h.rstrip("/"), h.replace("https://", "").rstrip("/")) else f"[{t}]({h})")
            else:
                rec(k)
    rec(n)
    return "\n".join(ws(l) for l in "".join(out).split("\n")).strip()


def az_norm(s):
    s = (s or "").replace("İ", "i").replace("I", "ı").lower()
    return ws(s.translate(str.maketrans("əışçğöü", "eiscgou")))


# ----------------------------------------------------------------- Bölmələr
MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avqust", "sentyabr", "oktyabr", "noyabr", "dekabr"]


def to_iso(s):
    m = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", s or "")
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s or "")
        if not m:
            return ""
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return datetime.date(y, mo, d).isoformat()
    except ValueError:
        return ""


def parse_registry(cont):
    tables = find(cont, "table", cls="reg-table") or \
        [t for t in find(cont, "table") if re.search(r"sirket|company", az_norm(text(t))[:400])]
    if not tables:
        return []
    t = tables[0]
    col = {"n": 0, "name": 1, "country": 2, "date": 3}
    rows = []
    for tr in find(t, "tr"):
        cells = [k for k in tr.kids if isinstance(k, Node) and k.tag in ("td", "th")]
        if not cells:
            continue
        if all(c.tag == "th" for c in cells):           # başlıq sətri — sütunların yerini tanı
            for i, c in enumerate(cells):
                h = az_norm(text(c))
                if "adi" in h or "sirket" in h or "name" in h or "company" in h: col["name"] = i
                elif "olke" in h or "country" in h: col["country"] = i
                elif "tarix" in h or "date" in h: col["date"] = i
                elif h in ("№", "no", "n", "s/s"): col["n"] = i
            continue
        v = [text(c) for c in cells]
        get = lambda k: v[col[k]] if col[k] < len(v) else ""
        name = get("name")
        if not name:
            continue
        n = get("n")
        rows.append([int(n) if n.isdigit() else len(rows) + 1, name, get("country") or "—", to_iso(get("date"))])
    return rows


def parse_faq(cont):
    scope = cont
    for d in find(cont, "details"):
        s = next((k for k in d.kids if isinstance(k, Node) and k.tag == "summary"), None)
        if s and re.search(r"tez-tez|frequently", az_norm(text(s))):
            scope = d
            break
    items, group, cur = [], "", None
    taken = set()                       # artıq cavaba daxil edilmiş elementlər (təkrar olmasın)

    def inside_taken(n):
        p = n.parent
        while p is not None and p is not scope:
            if id(p) in taken:
                return True
            p = p.parent
        return False

    def has_block(n):
        return any(k.tag in ("p", "ul", "ol", "div", "table") for k in walk(n))

    def add(n, t):
        taken.add(id(n))
        if t:
            cur["parts"].append(t)

    for n in walk(scope):
        c = n.cls
        if "section-badge" in c:
            group, cur = text(n), None
        elif n.tag == "p" and "faq-q" in c:
            cur = {"g": group, "q": re.sub(r"^\s*\d+\s*[.)]\s*", "", text(n)), "parts": []}
            items.append(cur)
        elif cur is None or inside_taken(n):
            continue
        elif (n.tag == "hr" and "faq-divider" in c) or n.tag in ("summary", "details", "table", "h1", "h2", "h3", "h4"):
            cur = None
        elif n.tag == "p":
            add(n, inline_md(n))
        elif n.tag in ("ul", "ol"):
            lis = [inline_md(li).replace("\n", " ") for li in n.kids if isinstance(li, Node) and li.tag == "li"]
            add(n, "\n".join("- " + x for x in lis if x))
        elif n.tag == "div" and not has_block(n):
            pills = [text(k) for k in walk(n) if "pill" in k.cls or "tag" in k.cls]
            add(n, "\n".join("- " + x for x in pills if x) if pills else inline_md(n))
        elif n.tag == "img" and n.attrs.get("src"):
            add(n, f"[{ws(n.attrs.get('alt')) or 'Nümunə / Sample'}]({absurl(n.attrs['src'])})")
    out = []
    for it in items:
        a = "\n".join(it["parts"]).strip()
        if it["q"]:
            out.append({"g": it["g"], "q": it["q"], "a": a, "h": faq_hash(it["q"], a)})
    return out


def faq_hash(q, a):
    return hashlib.sha1((ws(q) + "\n" + ws(a)).encode("utf-8")).hexdigest()[:12]


MONTHS_EN = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
# Hər dil üçün: (sualda axtarılan söz, cavabda rəqəmi tapan nümunə)
PATTERNS = {
    "az": {
        "DOVRIYYE_HEDDI": (r"dövriyyə həddi", r"(\d{1,3}(?:[\s\u00a0.,]\d{3})+|\d+)\s*ABŞ dollar"),
        "MECBURI_TARIX": (r"məcburi qeydiyyat", r"(\d{1,2})\s+(" + "|".join(MONTHS) + r")\s+(\d{4})"),
        "UCOT_MUDDETI": (r"uçotuna alınmaq|müəyyən edilmiş müddət", r"(\d{1,3})\s*gün ərzində"),
        "YOXLAMA_MUDDETI": (r"qeydiyyat nə qədər", r"(\d{1,3})\s*iş günü"),
        "BEYANNAME_GUNU": (r"bəyannamə\w*\s+nə vaxt", r"ayın\s*(\d{1,2})"),
        "EDV_DERECESI": (r"ƏDV dərəcəsi", r"(\d{1,2}(?:[.,]\d+)?)\s*(?:faiz|%)"),
        "VALYUTALAR": (r"hansı valyutada", None),
    },
    "en": {
        "DOVRIYYE_HEDDI": (r"turnover threshold", r"USD\s*(\d{1,3}(?:[\s\u00a0.,]\d{3})+|\d+)"),
        "MECBURI_TARIX": (r"mandatory registration", r"(\d{1,2})\s+(" + "|".join(MONTHS_EN) + r")\s+(\d{4})"),
        "UCOT_MUDDETI": (r"deadline for (?:tax )?registration|time to register", r"within\s+(\d{1,3})\s+days"),
        "YOXLAMA_MUDDETI": (r"how long", r"(\d{1,3})\s+working days"),
        "BEYANNAME_GUNU": (r"return be (?:submitted|filed)", r"(\d{1,2})(?:st|nd|rd|th)?\s+day"),
        "EDV_DERECESI": (r"VAT rate", r"(\d{1,2}(?:[.,]\d+)?)\s*(?:%|per ?cent)"),
        "VALYUTALAR": (r"which currency", None),
    },
}


def parse_params(cont, faq, lang="az"):
    p = {}
    P = PATTERNS[lang]
    months = MONTHS if lang == "az" else MONTHS_EN

    def item(pat):
        return next((f for f in faq if re.search(pat, f["q"], re.I)), None)

    def grab(key, conv, ok):
        pat_q, pat_a = P[key]
        f = item(pat_q)
        m = f and re.search(pat_a, f["a"], re.I)
        if not m:
            return None
        try:
            v = conv(m)
        except (ValueError, IndexError):
            return None
        if ok(v):
            p[key] = v

    num = lambda s: int(re.sub(r"[\s\u00a0.,]", "", s))
    grab("DOVRIYYE_HEDDI", lambda m: num(m.group(1)), lambda v: 100 <= v <= 10**8)
    grab("MECBURI_TARIX", lambda m: datetime.date(int(m.group(3)), months.index(m.group(2).lower()) + 1, int(m.group(1))).isoformat(), bool)
    grab("UCOT_MUDDETI", lambda m: int(m.group(1)), lambda v: 1 <= v <= 365)
    grab("YOXLAMA_MUDDETI", lambda m: int(m.group(1)), lambda v: 1 <= v <= 365)
    grab("BEYANNAME_GUNU", lambda m: int(m.group(1)), lambda v: 1 <= v <= 28)
    grab("EDV_DERECESI", lambda m: round(float(m.group(1).replace(",", ".")) / 100, 4), lambda v: 0 < v < 0.6)
    f = item(P["VALYUTALAR"][0])
    if f:
        codes = list(dict.fromkeys(re.findall(r"\(([A-Z]{3})\)", f["a"])))
        if codes: p["VALYUTALAR"] = ", ".join(codes)
    mails = [a.attrs["href"][7:].split("?")[0] for a in find(cont, "a") if a.attrs.get("href", "").startswith("mailto:")]
    mails = [m for m in mails if "@" in m]
    if mails:
        p["EPOCT"] = next((m for m in mails if "ecommerce" in m), mails[0])
    links = [absurl(a.attrs.get("href")) for a in find(cont, "a")]
    plat = next((h for h in links if re.match(r"https?://ecommerce\.", h or "")), None)
    if plat: p["PLATFORMA"] = plat.rstrip("/")
    docs = find(cont, "a", cls="doc-link")
    pay = r"payment|ödəniş"
    doc = next((a for a in docs if re.search(pay, a.attrs.get("href", ""), re.I)), None) or \
        next((a for a in docs if re.search(pay, text(a)[:80], re.I)), None)     # əvvəl linkin ünvanına, sonra mətninə görə
    if doc: p["ODENIS_TELIMATI"] = absurl(doc.attrs.get("href"))
    return p


def parse(src, lang="az"):
    root = build(src)
    cont = (find(root, id="page_container") or [root])[0]
    reg = parse_registry(cont)
    faq = parse_faq(cont)
    return reg, faq, parse_params(cont, faq, lang), block_lines(cont)


# ----------------------------------------------------------------- Yükləmə
def fetch(url, tries=5):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html", "Accept-Language": "az,en;q=0.8"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode(r.headers.get_content_charset() or "utf-8", errors="replace")
        except Exception as e:   # şəbəkə xətası — bir az gözləyib yenidən
            last = e
            time.sleep([5, 15, 30, 60, 90][min(i, 4)])
    raise RuntimeError(f"{url} açılmadı: {last}")


def load(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f) if path.endswith(".json") else f.read()
    except (OSError, ValueError):
        return default


def save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        if isinstance(data, str):
            f.write(data)
        else:
            f.write(json_dump(data))


def json_dump(o):
    """Oxunaqlı JSON: hər sətirdə bir yazı (git fərqləri aydın görünsün)."""
    if isinstance(o, list):
        return "[\n  " + ",\n  ".join(json.dumps(x, ensure_ascii=False) for x in o) + "\n]\n"
    parts = []
    for k, v in o.items():
        if isinstance(v, list) and v:
            parts.append(json.dumps(k) + ": [\n  " + ",\n  ".join(json.dumps(x, ensure_ascii=False) for x in v) + "\n]")
        else:
            parts.append(json.dumps(k) + ": " + json.dumps(v, ensure_ascii=False))
    return "{\n" + ",\n".join(parts) + "\n}\n"


def gh_output(**kw):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            for k, v in kw.items():
                f.write(f"{k}={'true' if v else 'false'}\n")


def warn(msg):
    print(f"::warning::{msg}" if os.environ.get("GITHUB_ACTIONS") else f"XƏBƏRDARLIQ: {msg}", file=sys.stderr)


# ----------------------------------------------------------------- Əsas
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=list(LANGS) + ["all"], default="all", help="hansı dil variantı yoxlanılsın (standart: hamısı)")
    ap.add_argument("--file", help="internetdən yükləmək əvəzinə yerli HTML faylını oxu")
    ap.add_argument("--today", help="tarixi əvəz et (sınaq üçün), YYYY-MM-DD")
    args = ap.parse_args()
    if args.file and args.lang == "all":
        if len(LANGS) > 1:
            ap.error("--file yalnız bir dil ilə istifadə olunur (--lang az)")
        args.lang = next(iter(LANGS))
    today = args.today or datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=4))).date().isoformat()  # Bakı vaxtı

    langs = list(LANGS) if args.lang == "all" else [args.lang]
    results = [sync_lang(lang, today, args.file) for lang in langs]
    reports = [r["report"] for r in results if r.get("report")]
    if reports:
        save(CHANGE, "\n\n---\n\n".join(reports))
    any_err = any(r["error"] for r in results)
    gh_output(updated=any(r["updated"] for r in results), changed=bool(reports), error=any_err)
    return 2 if (any_err and not os.environ.get("GITHUB_ACTIONS")) else 0   # GitHub-da xəta ayrıca addımda bildirilir


def sync_lang(lang, today, file=None):
    cfg = LANGS[lang]
    url = cfg["url"]
    d = os.path.join(ROOT, cfg["dir"])
    OUT, SNAP, BASE = os.path.join(d, "taxes.json"), os.path.join(d, "source-text.txt"), os.path.join(d, "faq-baseline.json")
    res = {"updated": False, "error": False, "report": None}
    tag = f"[{lang}]"
    try:
        src = open(file, encoding="utf-8").read() if file else fetch(url)
    except Exception as e:
        warn(f"{tag} Mənbə səhifə açılmadı, köhnə məlumat saxlanılır: {e}")
        return res

    reg, faq, params, lines = parse(src, lang)
    prev = load(OUT, {}) or {}
    warnings = []

    # Ehtiyat yoxlamaları: səhifənin quruluşu dəyişibsə, saytı sındırmırıq
    if not reg:
        print(f"XƏTA {tag}: reyestr cədvəli tapılmadı — taxes.gov.az səhifəsinin quruluşu dəyişib. Köhnə məlumat saxlanılır.", file=sys.stderr)
        res["error"] = True
        return res
    if len(prev.get("reg") or []) >= 5 and len(reg) < len(prev["reg"]) * 0.5:
        print(f"XƏTA {tag}: reyestrdə şübhəli azalma ({len(prev['reg'])} → {len(reg)}). Köhnə məlumat saxlanılır.", file=sys.stderr)
        res["error"] = True
        return res
    if len(faq) < 10:
        warnings.append(f"Sual-cavab bölməsi oxunmadı ({len(faq)} sual tapıldı) — saytdakı sual-cavablar dəyişmədən qalır.")
        faq = []
    if not any(r[3] for r in reg):
        warnings.append("Reyestrdə qeydiyyat tarixləri oxunmadı.")

    # Sual-cavab: ilkin (saytın hazırlandığı) rəsmi variantla müqayisə
    base = load(BASE)
    if base is None and faq:
        base = [{"g": f["g"], "q": f["q"], "h": f["h"]} for f in faq]
        save(BASE, base)
    used = set()
    out_faq = []
    for f in faq:
        idx = next((i for i, b in enumerate(base or []) if b["h"] == f["h"] and i not in used), None)
        if idx is not None:
            used.add(idx)
        out_faq.append({"g": f["g"], "q": f["q"], "a": f["a"], "base": idx})

    snapshot = "\n".join(lines) + "\n"
    h = hashlib.sha256(snapshot.encode("utf-8")).hexdigest()[:16]
    content_changed = bool(prev) and prev.get("hash") != h
    params["MELUMAT_TARIXI"] = today
    new = {
        "source": url,
        "checked": today,
        "changed": today if (content_changed or not prev) else prev.get("changed", today),
        "hash": h,
        "warnings": warnings,
        "params": [[k, v] for k, v in params.items()],
        "reg": reg,
        "faq": out_faq,
    }
    for w in warnings:
        warn(f"{tag} {w}")

    res["updated"] = json_dump(new) != json_dump(prev) if prev else True
    if res["updated"]:
        save(OUT, new)
    if content_changed or not os.path.exists(SNAP):
        old_snap = load(SNAP, "")
        save(SNAP, snapshot)
        if content_changed:
            res["report"] = change_report(prev, new, old_snap, snapshot, today, cfg["title"], url)
    print(f"{tag} Reyestr: {len(reg)} şirkət · Sual-cavab: {len(out_faq)} ({sum(1 for f in out_faq if f['base'] is None)} rəsmi mətnlə) · "
          f"Parametrlər: {len(params)} · {'DƏYİŞİKLİK VAR' if content_changed else 'dəyişiklik yoxdur'}")
    return res


def change_report(prev, new, old_snap, snap, today, title, url):
    d = lambda iso: ".".join(reversed(iso.split("-"))) if iso else ""
    L = [f"## taxes.gov.az səhifəsində dəyişiklik — {title}, {d(today)}", "",
         "Sayt avtomatik yeniləndi, sizdən heç nə tələb olunmur. Bu bildiriş yalnız məlumat üçündür.", ""]
    old = {r[1].lower(): r for r in prev.get("reg", [])}
    cur = {r[1].lower(): r for r in new["reg"]}
    add = [r for k, r in cur.items() if k not in old]
    rem = [r for k, r in old.items() if k not in cur]
    chg = [r for k, r in cur.items() if k in old and old[k] != r]
    if add or rem or chg:
        L.append("**Reyestr:**")
        L += [f"- ➕ {r[1]} ({r[2]}, {d(r[3])})" for r in add]
        L += [f"- ➖ {r[1]}" for r in rem]
        L += [f"- ✏️ {r[1]}: {r[2]}, {d(r[3])}" for r in chg]
        L.append("")
    pq = {f["q"]: f for f in prev.get("faq", [])}
    fq = [f for f in new["faq"] if f["q"] not in pq or pq[f["q"]].get("a") != f["a"]]
    if fq:
        L.append("**Sual-cavab (saytda artıq rəsmi mətn göstərilir):**")
        L += [f"- {f['q']}" for f in fq]
        L.append("")
    pp, np_ = dict(map(tuple, prev.get("params", []))), dict(map(tuple, new["params"]))
    pc = [k for k in np_ if k != "MELUMAT_TARIXI" and pp.get(k) != np_[k]]
    if pc:
        L.append("**Rəqəmlər / linklər:**")
        L += [f"- {k}: {pp.get(k, '—')} → {np_[k]}" for k in pc]
        L.append("")
    diff = list(difflib.unified_diff(old_snap.splitlines(), snap.splitlines(), "əvvəl", "indi", n=1, lineterm=""))
    if diff:
        body = diff[:200] + (["… (qısaldıldı)"] if len(diff) > 200 else [])
        L += ["<details><summary>Səhifə mətnindəki bütün fərqlər</summary>", "", "```diff", *body, "```", "</details>", ""]
    L.append(f"Mənbə: {url}")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
