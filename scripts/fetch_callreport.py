#!/usr/bin/env python
"""
Download one Call Report cycle from the FFIEC Central Data Repository.

    .venv/bin/python scripts/fetch_callreport.py --date 12/31/2025

Why this route rather than www.ffiec.gov/npw: NPW refuses automated clients
outright (HTTP 403 from a WAF, for every non-browser agent), and it is a
directory of institutions and ownership hierarchies rather than a source of
filings. The filings live in CDR, whose Public Data Distribution bulk download is
the access route FFIEC publishes for programmatic use — one ZIP per reporting
cycle holding every schedule for every filer.

CDR's download page is an ASP.NET WebForms app, so this walks the postback:
GET for the viewstate, POST to select the report series (which populates the
date list), then POST the chosen cycle and press Download.
"""
from __future__ import annotations

import argparse
import html
import http.cookiejar
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

URL = "https://cdr.ffiec.gov/public/PWS/DownloadBulkData.aspx"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
SERIES = "ReportingSeriesSinglePeriod"      # "Call Reports -- Single Period"
STATE_FIELDS = ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION")


def _state(page: str) -> dict[str, str]:
    out = {}
    for name in STATE_FIELDS:
        m = re.search(r'name="%s"[^>]*value="([^"]*)"' % re.escape(name), page)
        out[name] = html.unescape(m.group(1)) if m else ""
    return out


class CDR:
    def __init__(self) -> None:
        self.op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.op.addheaders = [("User-Agent", UA), ("Accept-Language", "en-US,en;q=0.9")]

    def get(self) -> str:
        return self.op.open(URL, timeout=120).read().decode("utf-8", "replace")

    def post(self, data: dict[str, str]):
        return self.op.open(urllib.request.Request(
            URL, data=urllib.parse.urlencode(data).encode(),
            headers={"User-Agent": UA, "Referer": URL, "Origin": "https://cdr.ffiec.gov",
                     "Content-Type": "application/x-www-form-urlencoded",
                     "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}), timeout=900)

    def cycles(self) -> tuple[list[tuple[str, str]], str]:
        """Available reporting cycles as (cycle_id, date) pairs, newest first."""
        d = _state(self.get())
        d["__EVENTTARGET"] = "ctl00$MainContentHolder$ListBox1"
        d["__EVENTARGUMENT"] = ""
        d["ctl00$MainContentHolder$ListBox1"] = SERIES
        page = self.post(d).read().decode("utf-8", "replace")
        pairs = re.findall(r'<option[^>]*value="(\d+)"[^>]*>\s*(\d{2}/\d{2}/\d{4})\s*</option>', page)
        return pairs, page

    def download(self, cycle_id: str, page: str, dest: Path) -> Path:
        d = _state(page)
        d["__EVENTTARGET"] = ""
        d["__EVENTARGUMENT"] = ""
        d["ctl00$MainContentHolder$ListBox1"] = SERIES
        d["ctl00$MainContentHolder$DatesDropDownList"] = cycle_id
        d["ctl00$MainContentHolder$FormatType"] = "TSVRadioButton"
        d["ctl00$MainContentHolder$TabStrip1$Download_0"] = "Download"
        r = self.post(d)
        disp = r.headers.get("Content-Disposition", "")
        if "attachment" not in disp.lower():
            raise SystemExit("CDR did not return a file; the form flow may have changed")
        dest.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        with dest.open("wb") as fh:
            while (chunk := r.read(1 << 20)):
                fh.write(chunk)
                total += len(chunk)
                print(f"\r  {total/1e6:.1f} MB", end="", file=sys.stderr, flush=True)
        print(f"\n  saved {dest} ({total/1e6:.1f} MB)", file=sys.stderr)
        return dest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", default="12/31/2025", help="cycle date, MM/DD/YYYY")
    ap.add_argument("--out", default="data/callreport.zip")
    ap.add_argument("--list", action="store_true", help="list available cycles and exit")
    args = ap.parse_args()

    cdr = CDR()
    pairs, page = cdr.cycles()
    if args.list:
        for cid, date in pairs:
            print(f"{cid}\t{date}")
        return
    match = next((c for c, d in pairs if d == args.date), None)
    if match is None:
        raise SystemExit(f"{args.date} not offered; try --list "
                         f"(newest is {pairs[0][1] if pairs else 'none'})")
    print(f"cycle {match} = {args.date}", file=sys.stderr)
    cdr.download(match, page, Path(args.out))


if __name__ == "__main__":
    main()
