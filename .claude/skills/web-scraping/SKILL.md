---
name: web-scraping
description: >-
  Discover how a public catalog or listing site serves its records, download
  them into a stable table, and report coverage against the site's own total.
  Use when the user asks to scrape, crawl, or download listings, search
  results, or a dataset from a website, including pagination, blocked pages,
  or an unknown API.
---

# Web scraping

Build a reproducible script that downloads a public result set into a table. Discover the request the site itself uses. This procedure names no site, no ids, and no field codes: read those from the page in front of you.

## Start from the page a person opens

1. Fetch the URL the user gave. Record status, final URL after redirects, and whether the body is the real result page or an interstitial (a challenge page, a captcha, or an empty shell).
2. Find where the records live:
   - JSON embedded in the first page (a preload, initial state, or `application/json` script).
   - The request fired when the page changes number. Search the page's scripts for `fetch(`, the pagination control, and the query object it sends.
3. Prefer that request over parsing result cards from HTML. Keep the filters the first page already applied.

## When a deep page is blocked

A new session, a new process, or a slower delay does not help if a fresh client, requesting only that deep page, still gets the interstitial while an early page returns records.

1. Compare one early page and one deep page on separate clients, at the same time.
2. If only the deep HTML is blocked, call the pagination request discovered above. That request often stays available after the HTML does not.
3. An automated browser that stops on a verification checkbox is a failed path. Leave the working client in place. A second client belongs behind the same interface, selected explicitly, and only after one deep page returns real records.

## Measure the page cap

The reported page count is not the number of pages that return new records.

1. Request page 1, a middle page, and a page past the advertised end.
2. Discard a response whose current page number is not the page you asked for.
3. Discard a page whose first record id matches an earlier page.
4. The cap is the last page that still returns new records.

## Cover a result set larger than the cap

Split with a filter the site already applies until each slice fits under the cap.

1. Read the filter values from the page state, a suggest endpoint, or the filter controls. Do not invent a fixed list.
2. Download every slice. Deduplicate by the record URL or id.
3. Compare the unique count with the total the site announces. If a slice's own total is large and its records are missing from the parent slice, that slice is not included in the parent: download it too.
4. Stop fetching a slice once its pages repeat.

Fetch pages in parallel only after one page of a slice returns records. Give each worker its own HTTP session. Retry a failed page a few times, then count failures instead of aborting the run. Expose the worker count as a flag.

## Output

Name each column for what it measures, not `field_0` / `field_1`. Map a source field by its id or label, not by the order it appears. Derive a column only when its inputs are present. Keep the raw value beside a parsed one, and leave the parsed column empty when the raw value is not in the unit the user asked for.

Save under the output directory the repo already uses, or `data/` when the repo has none. Print the path, the unique row count, the announced total, and how many pages failed.

## What to leave behind

- One documented command: `script <url> [--workers N]`.
- The discovery (request shape, cap, how the split was chosen) in the README in a few lines.
- No one-off downloader left beside the data. The split and the parallel fetch live in the scraper.
