#!/usr/bin/env python3
"""Self-test for the SAN parsers, using samples built from pages actually seen on Oct 28, 2026."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_sale as f  # noqa: E402

CATALOG = """
<h1>US 19th &amp; 20th Century Stamps continued...</h1>
<table>
<tr><th>Lot</th><th>Symbol</th><th>Lot Description</th><th>CV or Estimate</th></tr>
<tr><td>241</td><td>OVF-XF</td><td><a href="x.jpg"><img></a> 1a VF-XF 5&cent; gray brown Franklin imperf, light creases, blue grid cancel <a>(Image)</a><br>
 <a>Get Market Data for [United States 1a]</a></td>
 <td>Cat. US$565<br><b>Currently...$90.00</b><br>Will close during Public Auction</td></tr>
<tr><td>244</td><td>OVF</td><td>9 VF 1&cent; blue Franklin, 2016 PSE Cert <a>(Image)</a> Get Market Data</td>
 <td>Est. US$200-300<br><b>Currently...$80.00</b><br>Will close during Public Auction</td></tr>
<tr><td>243</td><td>OF-VF</td><td>5A F-VF 1&cent; blue Franklin</td>
 <td>Cat. US$6,000 SE<br><b>Currently...$300.00</b><br>Will close during Public Auction</td></tr>
<tr><td>511</td><td>x</td><td>NEWFOUNDLAND complete sheet of 40</td><td>Cat. Val. 11280.00 Currently C$ 2,300</td></tr>
<tr><td>600</td><td>x</td><td>No bid yet lot</td><td>Cat. US$100</td></tr>
<tr><td>2</td><td>x</td><td>Collection lot</td><td>SOLD for C$800.00 Will close during Public Auction</td></tr>
<tr><td>3</td><td>x</td><td>Face value lot</td><td>Cat. Val. 1600.00 SOLD for C$1,200.00 Will close during Public Auction</td></tr>
<tr><td>1433</td><td>x</td><td>40,\n42 F-VF odd\n lot</td><td>Pounds 778 SE Currently...$110.00 Will close during Public Auction</td></tr>
</table>
"""

RESULTS = """
<h1>Prices Realized for R. Maresch &amp; Son Auctions Ltd.'s Sale 592, October 28-29, 2026.</h1>
<a href="PricesRealizedWithPhotos.cfm">Prices Realized with Photos and Descriptions</a>
<a href="UnsoldsWithPhotos.cfm">*NEW* Unsold Lots with Photos and Descriptions</a>
<table><tr>
<td><table><tr><td>Lot No.</td><td>Realized</td></tr>
<tr><td>1</td><td>C$ 800</td></tr><tr><td>2</td><td>C$ 2,800</td></tr><tr><td>3</td><td>C$ 120</td></tr></table></td>
<td><table><tr><td>Lot No.</td><td>Realized</td></tr>
<tr><td>21</td><td>C$ 190</td></tr><tr><td>22</td><td>C$ 350</td></tr><tr><td>23</td><td>Unsold</td></tr></table></td>
</tr></table>
"""

FRONT = ('<a href="https://stampauctionnetwork.com/TS/ts36713.cfm#64">x</a> <a href="/TS/ts3671.cfm#1">y</a> '
         '<A HREF="ts36773.cfm">z</A> <A HREF="ts367100.cfm">w</A> <a href="https://StampAuctionNetwork.com/TS/TS367.cfm">home</a> '
         '<a href="https://stampauctionnetwork.com/RM/rm5921.cfm">other firm</a>')

ERROR_PAGE = "<h1>Prices Realized for StampAuctionNetwork's Sale 9999,</h1> Element SALE_DATE is undefined in SESSION."


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        check.failed = True


check.failed = False

sec, lots = f.parse_catalog_page(CATALOG, 13)
check("section heading", sec == "US 19th & 20th Century Stamps")
check("8 lots parsed", set(lots) == {"241", "244", "243", "511", "600", "1433", "2", "3"})
check("closed lot: 'SOLD for' read as a price, not a note", lots["2"]["sold"] == 800 and lots["2"]["cur"] == "C$" and "val_note" not in lots["2"] and "low" not in lots["2"])
check("closed lot with catalog value keeps both", lots["3"]["low"] == 1600 and lots["3"]["sold"] == 1200)
check("open lot has no sold price", "sold" not in lots["241"])
check("odd value wording kept as a note, not a number", "low" not in lots["1433"] and lots["1433"]["val_note"].startswith("Pounds 778") and lots["1433"]["bid"] == 110)
check("line breaks in description collapsed", lots["1433"]["desc"] == "40, 42 F-VF odd lot")
check("CV lot", lots["241"]["kind"] == "CV" and lots["241"]["low"] == 565 and lots["241"]["bid"] == 90)
check("currency US$", lots["241"]["cur"] == "US$")
check("estimate range", lots["244"]["kind"] == "EST" and lots["244"]["low"] == 200 and lots["244"]["high"] == 300)
check("thousands comma", lots["243"]["low"] == 6000 and lots["243"]["bid"] == 300)
check("Maresch 'Cat. Val.' + 'Currently C$ 2,300'", lots["511"]["low"] == 11280 and lots["511"]["bid"] == 2300 and lots["511"]["cur"] == "C$")
check("lot with no bid has no bid key", "bid" not in lots["600"])
check("description cleaned", "(Image)" not in lots["241"]["desc"] and "Get Market" not in lots["241"]["desc"])

p = f.parse_results(RESULTS, "592")
check("handshake ok for right sale", p["handshake_ok"])
check("results pairs", p["results"]["2"] == {"amount": 2800.0, "cur": "C$"} and p["results"]["22"]["amount"] == 350)
check("header words ignored", "Lot No." not in p["results"] and len(p["results"]) == 6)
check("unsold word recorded", p["results"]["23"] == {"status": "unsold"})
check("unsold link found", p["unsold_href"] == "UnsoldsWithPhotos.cfm")
check("handshake fails on wrong sale", not f.parse_results(RESULTS, "367")["handshake_ok"])
check("handshake fails on error page", not f.parse_results(ERROR_PAGE, "367")["handshake_ok"])

links = f.catalog_page_links(FRONT, "TS", "367")
check("catalog links: absolute + bare relative, deduped, sorted, home page and other firms ignored", [n for n, _ in links] == [1, 13, 73, 100])
check("catalog link rebuilt as full path", links[0][1] == "/TS/ts3671.cfm")
rl = f.catalog_page_links('<A HREF="rm59219.cfm">a</A> <a href="RM592.cfm">b</a>', "RM", "592")
check("Maresch-style links", [n for n, _ in rl] == [19])

check("unsold lot numbers", f.parse_unsold("<p>Lot 88 something</p><table><tr><td>90</td><td>x</td></tr></table>") == ["88", "90"])

import datetime as _dt
_t1 = _dt.datetime(2026, 11, 10, 15, 0, tzinfo=_dt.timezone.utc)
_t2 = _t1 + _dt.timedelta(minutes=20)
_o = {"results": {"1": {"amount": 800.0}, "2": {"status": "unsold"}}, "lots": {"3": {"sold": 120.0}, "4": {"bid": 5.0}}}
f.stamp_sold_seen(_o, _t1)
check("first-seen stamps: results + catalog sold only", set(_o["sold_seen"]) == {"1", "3"})
_o["results"]["5"] = {"amount": 9.0}
f.stamp_sold_seen(_o, _t2)
check("first-seen stamp is never overwritten", _o["sold_seen"]["1"] == "2026-11-10T15:00:00Z" and _o["sold_seen"]["5"] == "2026-11-10T15:20:00Z")

if check.failed:
    sys.exit(1)
print("All parser self-tests passed.")
