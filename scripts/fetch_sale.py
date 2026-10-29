#!/usr/bin/env python3
"""Fetch catalog bids and prices-realized for sales listed in sales.json.

Writes one JSON file per sale into data/. Meant to run on a schedule in
GitHub Actions, but it also runs fine on any computer with Python 3.10+:

    pip install requests beautifulsoup4
    python scripts/fetch_sale.py --force

How StampAuctionNetwork (SAN) works, as observed:
  * The "Realizations" button on a sale page is a form POST to
    /pricesrealized.cfm with the field  posted=Realizations .
  * SAN remembers WHICH sale you mean in a session cookie that it hands out
    when you load the sale page. So we load the sale page first, keep the
    cookies (requests.Session does that for us), then POST.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://stampauctionnetwork.com"
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
DELAY = float(os.environ.get("SAN_DELAY_SECONDS", "1.2"))  # pause between requests
UA = os.environ.get(
    "SAN_USER_AGENT",
    "StampTracker/1.0 (personal consignor tracker; polite, low-volume)",
)

CUR = r"(?:US\s?\$|C\s?\$|A\s?\$|NZ\s?\$|£|€|\$)"
AMT = r"\d[\d,]*(?:\.\d+)?"
CV_RE = re.compile(
    rf"(Cat\.?(?:\s*Val\.?)?|Est\.?)\s*({CUR})?\s*({AMT})(?:\s*-\s*(?:{CUR})?\s*({AMT}))?",
    re.I,
)
BID_RE = re.compile(rf"Currently\.*\s*({CUR})?\s*({AMT})", re.I)
SOLD_RE = re.compile(rf"SOLD\s+for\s*({CUR})?\s*({AMT})", re.I)
# Currency is required: a bare "6" next to a lot number is far more likely a neighbouring lot than a price.
RESULT_AMT_RE = re.compile(rf"^({CUR})\s*({AMT})$", re.I)
LOT_RE = re.compile(r"^\d+[A-Za-z]?$")
STATUS_WORDS = re.compile(r"^(unsold|passed|pass|withdrawn|no sale|not sold)$", re.I)


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    if not s:
        return None
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def num(s):
    return float(s.replace(",", "")) if s else None


def norm_cur(c):
    return re.sub(r"\s", "", c) if c else ""


# --------------------------------------------------------------------------
# Parsers (pure functions, covered by scripts/test_parsers.py)
# --------------------------------------------------------------------------

def parse_catalog_page(html: str, page_no: int):
    """Return (section, {lot: {...}}) for one catalog page."""
    soup = BeautifulSoup(html, "html.parser")
    section = ""
    for h in soup.find_all(["h1", "h2"]):
        t = h.get_text(" ", strip=True)
        if t and "StampAuction" not in t and "Sale -" not in t:
            section = re.sub(r"\s*continued\.*\s*$", "", t, flags=re.I)
            break
    lots = {}
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        if len(tds) < 3:
            continue
        lot = tds[0].get_text(" ", strip=True)
        if not LOT_RE.match(lot):
            continue
        desc_td, val_td = tds[-2], tds[-1]
        desc = re.sub(r"\s+", " ", desc_td.get_text(" ", strip=True))
        desc = re.split(r"\(Image\)|Get Market Data", desc)[0].strip()
        cell = re.sub(r"\s+", " ", val_td.get_text(" ", strip=True))
        rec = {"desc": desc, "page": page_no, "section": section}
        # Second cell = SAN's "Symbol" column (condition, e.g. "OVF-XF", "**", "*O"). Often empty on covers.
        if len(tds) >= 4:
            sym = re.sub(r"\s+", " ", tds[1].get_text(" ", strip=True))
            if sym:
                rec["sym"] = sym
        m = CV_RE.search(cell)
        if m:
            kind = "CV" if m.group(1).lower().startswith("cat") else "EST"
            rec.update(kind=kind, cur=norm_cur(m.group(2)), low=num(m.group(3)), high=num(m.group(4)))
        # Closed lots read e.g. "SOLD for C$800.00 Will close during Public Auction" (seen on live SAN).
        sd = SOLD_RE.search(cell)
        if sd:
            rec["sold"] = num(sd.group(2))
            if not rec.get("cur"):
                rec["cur"] = norm_cur(sd.group(1))
        if not m:
            # Unusual value wording, e.g. "Pounds 778 SE Currently...$110.00". Keep the text but
            # do NOT turn it into a number: it may be in a different currency than the bids.
            rest = SOLD_RE.sub(" ", BID_RE.sub(" ", cell))
            rest = re.sub(r"Will close during Public Auction|Closing|Closed", " ", rest, flags=re.I)
            rest = re.sub(r"\s+", " ", rest).strip()
            if rest:
                rec["val_note"] = rest
        b = BID_RE.search(cell)
        if b:
            rec["bid"] = num(b.group(2))
            if not rec.get("cur"):
                rec["cur"] = norm_cur(b.group(1))
        lots[lot] = rec
    return section, lots


def parse_results(html: str, sale: str):
    """Parse the Prices Realized grid. Returns dict with title, handshake flag, results."""
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else ""
    ok = bool(re.search(r"Prices Realized for", title, re.I)) and bool(
        re.search(rf"Sale\s+{re.escape(sale)}\b", title, re.I)
    )
    cells = [c.get_text(" ", strip=True) for c in soup.find_all("td")]
    results, i = {}, 0
    while i < len(cells) - 1:
        if LOT_RE.match(cells[i]):
            nxt = cells[i + 1]
            m = RESULT_AMT_RE.match(nxt)
            if m:
                results[cells[i]] = {"amount": num(m.group(2)), "cur": norm_cur(m.group(1))}
                i += 2
                continue
            if STATUS_WORDS.match(nxt):
                results[cells[i]] = {"status": nxt.lower()}
                i += 2
                continue
        i += 1
    unsold_href = None
    for a in soup.find_all("a"):
        if re.search(r"unsold", a.get_text(" ", strip=True), re.I) and a.get("href"):
            unsold_href = a["href"]
            break
    return {"title": title, "handshake_ok": ok, "results": results, "unsold_href": unsold_href}


def lot_sort_key(s):
    return (int(re.match(r"\d+", s).group()), s)


UNSOLD_TOTAL_RE = re.compile(r"Displaying records\s+(\d+)\s+to\s+(\d+)\s+of\s+(\d+)\s+Total Records", re.I)
UNSOLD_PAGE_RE = re.compile(r"UnsoldsWithPhotos\.cfm\?pageno=(\d+)", re.I)


def parse_unsold_page(html: str):
    """Parse one page of SAN's 'Unsold Lots with Photos and Descriptions' (layout seen Oct 28, 2026).

    IMPORTANT: this page lists every lot that has NOT SOLD, which includes lots that have not
    closed yet. Before a sale starts it lists the whole catalog (50 per page). Callers must not
    treat these lots as unsold until the sale has moved past them (see unsold_below()).

    Each entry looks like  <td><b>Lot 12</b></td>  with the description underneath.
    Returns {"lots": [...], "total": int|None, "pages": int}.
    """
    soup = BeautifulSoup(html, "html.parser")
    lots = set()
    for b in soup.find_all("b"):
        m = re.match(r"^Lot\s+(\d+[A-Za-z]?)$", b.get_text(" ", strip=True), re.I)
        if m:
            lots.add(m.group(1))
    if not lots:  # layout changed: fall back to the looser reading
        text = soup.get_text(" ", strip=True)
        lots = set(re.findall(r"\bLot\s*(?:No\.?|#)?\s*(\d+[A-Za-z]?)\b", text, re.I))
        for tr in soup.find_all("tr"):
            tds = tr.find_all("td", recursive=False)
            if tds and LOT_RE.match(tds[0].get_text(" ", strip=True)):
                lots.add(tds[0].get_text(" ", strip=True))
    t = UNSOLD_TOTAL_RE.search(soup.get_text(" ", strip=True))
    pages = [int(n) for n in UNSOLD_PAGE_RE.findall(html)]
    return {
        "lots": sorted(lots, key=lot_sort_key),
        "total": int(t.group(3)) if t else None,
        "pages": max(pages) if pages else 1,
    }


def parse_unsold(html: str):
    """Lot numbers on one Unsold page (kept for the self-test; see parse_unsold_page)."""
    return parse_unsold_page(html)["lots"]


def sold_frontier(out):
    """Highest lot number known to have SOLD (results page or catalog 'SOLD for'), or None.

    Sales close in lot order, so a lot below this number that did not sell has really
    passed. A lot above it may simply not have closed yet.
    """
    best = None
    for lot, r in out.get("results", {}).items():
        if r.get("amount") is not None:
            best = max(best, lot_sort_key(lot)[0]) if best is not None else lot_sort_key(lot)[0]
    for lot, rec in out.get("lots", {}).items():
        if rec.get("sold") is not None:
            best = max(best, lot_sort_key(lot)[0]) if best is not None else lot_sort_key(lot)[0]
    return best


def unsold_below(unsold_lots, frontier):
    """Keep only unsold-page lots the sale has already moved past."""
    if frontier is None:
        return []
    return [l for l in unsold_lots if lot_sort_key(l)[0] < frontier]


def read_unsold(s, href, out, meta, key, debug=False, max_pages=40):
    """Read the Unsold pages far enough to cover every lot below the sold frontier."""
    frontier = sold_frontier(out)
    url = urljoin(BASE + "/", href)
    u = get(s, url)
    first = parse_unsold_page(u.text)
    meta["unsold_total"] = first["total"]
    meta["unsold_format"] = "table of <b>Lot N</b> entries, 50 per page (verified layout)"
    print(f"[{key}] unsold page 1: HTTP {u.status_code}, {len(first['lots'])} lots listed, {first['total']} not sold in all, {first['pages']} pages")
    if debug:
        (RAW / f"{key}-unsold.html").write_text(u.text)
    if frontier is None:
        # Nothing has sold yet: the page just lists the whole catalog. Saving it would mark lots unsold.
        out["unsold"] = []
        meta["unsold_note"] = "not read yet: no lot has sold, so every lot is simply still open"
        return
    meta.pop("unsold_note", None)
    found = list(first["lots"])
    page, last_lot = 1, (lot_sort_key(first["lots"][-1])[0] if first["lots"] else -1)
    while last_lot < frontier and page < min(first["pages"], max_pages):
        page += 1
        r = get(s, urljoin(BASE + "/", f"UnsoldsWithPhotos.cfm?pageno={page}"))
        p = parse_unsold_page(r.text)
        if not p["lots"]:
            meta["warnings"].append(f"Unsold page {page} had no lots; stopped reading there.")
            break
        found += p["lots"]
        last_lot = lot_sort_key(p["lots"][-1])[0]
    out["unsold"] = unsold_below(sorted(set(found), key=lot_sort_key), frontier)
    print(f"[{key}] unsold read through page {page}; {len(out['unsold'])} lots below sold frontier (lot {frontier})")


def catalog_page_links(html: str, firm: str, sale: str):
    """Find paged catalog URLs on the sale's front page.

    SAN writes them as bare relative links (HREF="ts36773.cfm", HREF="rm59219.cfm"),
    and sometimes as full addresses (.../TS/ts36772.cfm#Lot1422). Match both.
    """
    pat = re.compile(rf"(?<![A-Za-z0-9]){re.escape(firm.strip())}{re.escape(sale)}(\d+)\.cfm", re.I)
    pages = sorted({int(m.group(1)) for m in pat.finditer(html)})
    f = firm.strip()
    return [(n, f"/{f}/{f.lower()}{sale}{n}.cfm") for n in pages]


# --------------------------------------------------------------------------
# Network
# --------------------------------------------------------------------------

def make_session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    return s


def get(s, url, **kw):
    last = None
    for attempt in range(3):
        try:
            r = s.get(url, timeout=30, **kw)
            if r.status_code < 500:
                time.sleep(DELAY)
                return r
            last = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            last = str(e)
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"GET {url} failed: {last}")


def post_realizations(s, sale_url):
    r = s.post(
        f"{BASE}/pricesrealized.cfm",
        data={"posted": "Realizations"},
        headers={"Referer": sale_url, "Origin": BASE},
        timeout=30,
    )
    time.sleep(DELAY)
    return r


# --------------------------------------------------------------------------
# One sale
# --------------------------------------------------------------------------

def run_sale(cfg, force=False, debug=False):
    key, firm, sale = cfg["key"], cfg["firm"], str(cfg["sale"])
    sale_url = cfg.get("sale_url") or f"{BASE}/{firm}/{firm}{sale}.cfm"
    t = now_utc()
    start, end = parse_iso(cfg.get("track_from")), parse_iso(cfg.get("track_until"))
    if not force:
        if start and t < start:
            print(f"[{key}] before tracking window, skipping")
            return True
        if end and t > end:
            print(f"[{key}] after tracking window, skipping")
            return True

    path = DATA / f"{key}.json"
    prev = json.loads(path.read_text()) if path.exists() else {}
    meta_prev = prev.get("meta", {})
    out = {
        "meta": {
            "key": key, "firm": firm, "sale": sale, "label": cfg.get("label", key),
            "sale_url": sale_url, "warnings": [],
        },
        "lots": prev.get("lots", {}),
        "results": prev.get("results", {}),
        "unsold": prev.get("unsold", []),
        "history": prev.get("history", {}),
    }
    meta = out["meta"]
    for k in ("catalog_fetched_at", "results_fetched_at"):
        if meta_prev.get(k):
            meta[k] = meta_prev[k]
    ok = True
    s = make_session()
    RAW.mkdir(parents=True, exist_ok=True)

    # 1. Load the sale front page: gives us cookies + the list of catalog pages.
    front = get(s, sale_url)
    print(f"[{key}] sale page: HTTP {front.status_code}, {len(front.text)} bytes, cookies: {sorted(s.cookies.keys())}")
    if front.status_code != 200:
        meta["warnings"].append(f"Sale page returned HTTP {front.status_code}")
        write(path, out)
        return False

    # 2. Results (needs the session set up in step 1).
    unsold_href = None
    results_from = parse_iso(cfg.get("results_from"))
    if force or not results_from or t >= results_from:
        # A SAN hiccup here must not stop the catalog and unsold steps below, so it is caught, not raised.
        try:
            r = post_realizations(s, sale_url)
            print(f"[{key}] realizations POST: HTTP {r.status_code}, {len(r.text)} bytes")
            parsed = parse_results(r.text, sale)
            print(f"[{key}] results title: {parsed['title']!r}")
            if parsed["handshake_ok"]:
                print(f"[{key}] HANDSHAKE_OK - SAN returned the right sale ({len(parsed['results'])} results)")
                # Merge rather than replace: a short or partial page from SAN must never erase results
                # already collected. A lot whose entry changes (e.g. to "unsold") is still updated.
                out["results"] = {**out.get("results", {}), **parsed["results"]}
                meta["results_fetched_at"] = iso(t)
                unsold_href = parsed["unsold_href"]
            else:
                print(f"[{key}] HANDSHAKE_FAILED - results page did not name sale {sale}")
                meta["warnings"].append("Realizations page did not return this sale (session handshake failed).")
                (RAW / f"{key}-results-failed.html").write_text(r.text)
                ok = False
            if debug or not parsed["results"]:
                (RAW / f"{key}-results.html").write_text(r.text)
        except Exception as e:  # noqa: BLE001
            print(f"[{key}] results step failed: {e}")
            meta["warnings"].append(f"Results step failed ({e}); kept the previous results.")
            ok = False

    # 3. Catalog pages (bids). Only if due. "Live" runs from results_from to sale_end (if given); after the
    # main sale the slower pre-sale rate applies again, so a week of post-sale tracking stays light on SAN.
    sale_end = parse_iso(cfg.get("sale_end"))
    live = bool(results_from and t >= results_from and (not sale_end or t < sale_end))
    every = cfg.get("catalog_refresh_minutes_live" if live else "catalog_refresh_minutes", 60)
    last = parse_iso(meta_prev.get("catalog_fetched_at"))
    # The cron fires every ~15 min with a few minutes of jitter, so allow 3 min of slack; otherwise a
    # "15 minute" setting would quietly become 30.
    due = force or not last or (t - last).total_seconds() >= every * 60 - 180
    if due:
        pages = catalog_page_links(front.text, firm, sale)
        print(f"[{key}] catalog pages found: {len(pages)}")
        if not pages:
            meta["warnings"].append("No catalog page links found on the sale front page.")
            ok = False
        got = 0
        for n, href in pages:
            try:
                r = get(s, urljoin(BASE + "/", href.lstrip("/")))
                if r.status_code != 200:
                    meta["warnings"].append(f"Catalog page {n}: HTTP {r.status_code}")
                    continue
                if debug and n == pages[0][0]:
                    (RAW / f"{key}-catalog-sample.html").write_text(r.text)
                _, lots = parse_catalog_page(r.text, n)
                if not lots:
                    meta["warnings"].append(f"Catalog page {n}: no lots parsed")
                for lot, rec in lots.items():
                    out["lots"][lot] = rec
                    h = out["history"].setdefault(lot, [])
                    if "bid" in rec and (not h or h[-1][1] != rec["bid"]):
                        h.append([iso(t), rec["bid"]])
                got += 1
            except Exception as e:  # noqa: BLE001
                meta["warnings"].append(f"Catalog page {n}: {e}")
        meta["catalog_fetched_at"] = iso(t)
        meta["catalog_pages"] = got
        print(f"[{key}] catalog: {got}/{len(pages)} pages, {len(out['lots'])} lots")
    else:
        print(f"[{key}] catalog not due (every {every} min)")

    # 4. Unsold lots. Done last because it needs to know how far the sale has got (see read_unsold).
    if unsold_href:
        try:
            read_unsold(s, unsold_href, out, meta, key, debug=debug)
        except Exception as e:  # noqa: BLE001
            meta["warnings"].append(f"Unsold page failed: {e}")
            out["unsold"] = unsold_below(out.get("unsold", []), sold_frontier(out))  # never keep a stale list
    elif "unsold" in out:
        out["unsold"] = unsold_below(out["unsold"], sold_frontier(out))  # also cleans old saved data

    out["sold_seen"] = prev.get("sold_seen", {})
    stamp_sold_seen(out, t)
    meta["fetched_at"] = iso(t)
    meta["lot_count"] = len(out["lots"])
    meta["result_count"] = len(out["results"])
    write(path, out)
    return ok


def stamp_sold_seen(out, t):
    """Remember when each lot was FIRST seen as sold (results page or catalog 'SOLD for').

    Used by the dashboard's 'Just sold' ticker and its pace estimate. The resolution is the
    job's schedule (about 15-20 minutes), not the exact second the hammer fell.
    """
    seen = out.setdefault("sold_seen", {})
    for lot, r in out.get("results", {}).items():
        if r.get("amount") is not None:
            seen.setdefault(lot, iso(t))
    for lot, rec in out.get("lots", {}).items():
        if rec.get("sold") is not None:
            seen.setdefault(lot, iso(t))


def write(path: Path, obj):
    DATA.mkdir(exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":"), sort_keys=True))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="ignore tracking window and refresh timers")
    ap.add_argument("--debug", action="store_true", help="save raw HTML samples to data/raw/")
    ap.add_argument("--only", help="only this sale key")
    a = ap.parse_args()
    sales = json.loads((ROOT / "sales.json").read_text())["sales"]
    all_ok = True
    for cfg in sales:
        if a.only and cfg["key"] != a.only:
            continue
        try:
            all_ok &= run_sale(cfg, force=a.force, debug=a.debug or a.force)
        except Exception as e:  # noqa: BLE001
            print(f"[{cfg['key']}] ERROR: {e}")
            all_ok = False
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
