#!/usr/bin/env python3
"""
Bulk-download TfNSW Opal Patronage daily files (Jan 2020 -> today).

Usage:
    python3 download_opal.py

Only uses the Python standard library. Resumable: re-run it any time,
already-downloaded files are skipped. Files are saved to ./opal_data/raw/.

Per TfNSW instructions, programmatic downloads must send the referrer
header "https://opendata.transport.nsw.gov.au/".
"""

import concurrent.futures as cf
import datetime as dt
import os
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

BASE = "https://opendata-tpa.transport.nsw.gov.au"
PREFIX = "Opal_Patronage"
HEADERS = {
    "Referer": "https://opendata.transport.nsw.gov.au/",
    "User-Agent": "opal-analysis-personal-project/1.0",
}
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "raw")
START_DATE = dt.date(2020, 1, 1)
MAX_WORKERS = 8
MIN_VALID_BYTES = 200  # anything smaller is likely an error page


def http_get(url, timeout=60):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def list_bucket_keys():
    """Try S3 ListObjectsV2 to discover the real file keys. Returns [] on failure."""
    keys, token = [], None
    try:
        while True:
            url = f"{BASE}/?list-type=2&prefix={PREFIX}&max-keys=1000"
            if token:
                from urllib.parse import quote
                url += f"&continuation-token={quote(token)}"
            data = http_get(url)
            root = ET.fromstring(data)
            ns = {"s3": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}
            def findall(tag):
                return root.findall(f"s3:{tag}", ns) if ns else root.findall(tag)
            def findtext(tag):
                el = root.find(f"s3:{tag}", ns) if ns else root.find(tag)
                return el.text if el is not None else None
            for c in findall("Contents"):
                k = c.find("s3:Key", ns) if ns else c.find("Key")
                if k is not None and k.text and k.text.endswith(".txt"):
                    keys.append(k.text)
            if findtext("IsTruncated") == "true":
                token = findtext("NextContinuationToken")
                if not token:
                    break
            else:
                break
    except Exception as e:
        print(f"[i] Bucket listing unavailable ({e.__class__.__name__}: {e}); "
              f"falling back to date-constructed URLs.")
        return []
    return keys


def candidate_urls_for_date(d):
    stamp = d.strftime("%Y%m%d")
    fname = f"{PREFIX}_{stamp}.txt"
    return fname, [
        f"{BASE}/{PREFIX}/{fname}",
        f"{BASE}/{fname}",
    ]


def download_one(job):
    fname, urls = job
    dest = os.path.join(OUT_DIR, fname)
    if os.path.exists(dest) and os.path.getsize(dest) >= MIN_VALID_BYTES:
        return ("skipped", fname)
    last_err = "unknown"
    for url in urls:
        for attempt in range(3):
            try:
                data = http_get(url)
                if len(data) < MIN_VALID_BYTES or not data.lstrip()[:20].startswith(b"trip_origin_date"):
                    last_err = f"unexpected content ({len(data)} bytes)"
                    break  # wrong URL pattern or bad payload; try next URL
                with open(dest, "wb") as f:
                    f.write(data)
                return ("ok", fname)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    last_err = "404"
                    break  # try next URL pattern
                last_err = f"HTTP {e.code}"
                time.sleep(1 + attempt)
            except Exception as e:
                last_err = f"{e.__class__.__name__}"
                time.sleep(1 + attempt)
    return ("failed: " + last_err, fname)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    today = dt.date.today()

    keys = list_bucket_keys()
    if keys:
        print(f"[i] Bucket listing worked: {len(keys)} files found.")
        jobs = [(k.split("/")[-1], [f"{BASE}/{k}"]) for k in keys]
    else:
        dates, d = [], START_DATE
        while d <= today:
            dates.append(d)
            d += dt.timedelta(days=1)
        jobs = [candidate_urls_for_date(x) for x in dates]
        print(f"[i] Trying {len(jobs)} date-constructed URLs "
              f"({START_DATE} -> {today}).")

    ok = skipped = 0
    failures = []
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for i, (status, fname) in enumerate(ex.map(download_one, jobs), 1):
            if status == "ok":
                ok += 1
            elif status == "skipped":
                skipped += 1
            else:
                failures.append((fname, status))
            if i % 200 == 0:
                print(f"    ... {i}/{len(jobs)} processed "
                      f"({ok} downloaded, {skipped} skipped, {len(failures)} failed)")

    print(f"\nDone in {time.time()-t0:.0f}s: {ok} downloaded, {skipped} already present, "
          f"{len(failures)} failed, saved in {OUT_DIR}")
    if failures:
        log = os.path.join(OUT_DIR, "_failures.log")
        with open(log, "w") as f:
            for fname, status in failures:
                f.write(f"{fname}\t{status}\n")
        print(f"[!] Failure list written to {log}")
        only_404 = all(s.endswith("404") for _, s in failures)
        if only_404 and len(failures) < 60:
            print("[i] Small number of 404s usually just means those dates "
                  "were never published (normal).")


if __name__ == "__main__":
    main()
