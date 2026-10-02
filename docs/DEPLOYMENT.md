# Deploying TileIQ — step by step

The interface is a **static site**: HTML, CSS, JavaScript, JSON and images. No server, no database,
nothing to pay for. The only machine that runs code is the one that refreshes the data, and that can
be an office PC.

Everything below is free. Total cost: **LKR 0 per month.**

---

## What gets deployed

| Folder | Contents | Size |
|---|---|---|
| `site/index.html`, `app.js`, `styles.css` | the interface | ~100 KB |
| `site/data/*.json` | every number the pages draw | ~1.8 MB |
| `site/img/*.jpg` | 3,490 tile thumbnails | ~66 MB |

**~68 MB and 3,535 files in total** — comfortably inside every free host's limits (Cloudflare Pages
allows 20,000 files and 25 MB per file).

What is **not** deployed, and never committed: `data/raw/` (the 1.1 GB page cache),
`data/processed/` (working files) and `data/images/` (the local thumbnail cache that `site/img/` is
built from). `.gitignore` already excludes them.

---

## Part 1 — Put the project on GitHub (10 minutes)

### 1.1 Confirm the build is current

```bash
cd "C:\Users\Vinura Jayewardene\Documents\Tech\AI\Lanka Tiles Sales Analytics"
python -m tileiq.pipeline
```

It should finish with a summary ending in `spot_check: matched`. Then check it locally:

```bash
python -m http.server 8765 --directory site
```

Open `http://localhost:8765` and confirm the Overview loads and the Price audit page shows today's
build time. Press Ctrl+C to stop.

> The site must be served over HTTP. Opening `site/index.html` directly from the file system will
> show an empty page, because browsers block `fetch()` on `file://` URLs.

### 1.2 Commit

```bash
git add -A
git commit -m "TileIQ build"
```

### 1.3 Create a private GitHub repository

On github.com: **New repository** → name it `tileiq` → **Private** → don't add a README → Create.

> Keep it private. The underlying pages are public, but the analysis is not something to hand to
> Macktiles.

### 1.4 Push

```bash
git remote add origin https://github.com/<your-account>/tileiq.git
git branch -M main
git push -u origin main
```

The first push uploads about 68 MB and takes a few minutes.

---

## Part 2 — Publish on Cloudflare Pages (10 minutes)

Free tier: unlimited bandwidth, 500 builds a month, and access control for up to 50 users.

### 2.1 Connect the repo

1. Sign up free at **dash.cloudflare.com**.
2. **Workers & Pages** → **Create** → **Pages** → **Connect to Git**.
3. Authorise GitHub, select the `tileiq` repository.
4. Build settings — this is the important screen:
   - **Framework preset:** `None`
   - **Build command:** *leave completely empty*
   - **Build output directory:** `site`
5. **Save and Deploy.**

After about a minute you get a live URL like `https://tileiq-a1b.pages.dev`.

### 2.2 Lock it to your team (do this before sharing the link)

Until you do this, anyone with the URL can read it.

1. Cloudflare dashboard → **Zero Trust** → **Access** → **Applications** → **Add an application** →
   **Self-hosted**.
2. **Application name:** TileIQ. **Domain:** paste your `pages.dev` hostname.
3. **Add policy** → Name: `Vallibel One staff`, Action: **Allow**.
4. **Include** → **Emails ending in** → `@vallibelone.com` (or **Emails** and list the leadership
   team individually).
5. Save. Visitors now get a one-time email code before the site opens. Free for up to 50 users.

### 2.3 Optional — your own domain

If a company domain is already on Cloudflare: Pages → your project → **Custom domains** → add
`tileiq.vallibelone.com`. The certificate is issued automatically, free.

---

## Part 3 — Keep the data fresh

Three commands, deliberately different in cost:

| Command | Re-fetches | Time | Works on a clean clone? |
|---|---|---|---|
| `python -m tileiq.pipeline` | nothing — rebuilds from the local cache | ~2 min | No |
| `python -m tileiq.pipeline --refresh-prices` | only the sources that publish prices (BuyRocell, Mascons) | ~10 min | No |
| `python -m tileiq.pipeline --refresh` | every catalogue, the global benchmark and marketing | 2–3 hrs | Yes |

**The important caveat:** the first two rebuild from `data/raw/`, which is *not* in the repository
because it is 1.1 GB. They only work on the machine that has the cache — normally the office PC that
first built the project. A clean clone (or a GitHub Actions runner) must use `--refresh`.

That leads to two workable patterns. Pick one.

### Option A — Refresh on an office PC (recommended)

The machine already has the cache, so nightly refreshes are quick and cheap.

Open a terminal **in the project folder** and run these once:

```bash
schtasks /create /tn "TileIQ nightly prices" /tr "cmd /c cd /d \"%CD%\" && python -m tileiq.pipeline --refresh-prices && git add -A && git commit -m \"nightly price refresh\" && git push" /sc daily /st 02:00 /rl highest
```

```bash
schtasks /create /tn "TileIQ weekly full refresh" /tr "cmd /c cd /d \"%CD%\" && python -m tileiq.pipeline --refresh && git add -A && git commit -m \"weekly full refresh\" && git push" /sc weekly /d SUN /st 01:00 /rl highest
```

Each push triggers Cloudflare Pages to redeploy automatically — usually live within two minutes.
The PC must be switched on at those times.

To check the schedules later: `schtasks /query /tn "TileIQ nightly prices"`.
To remove one: `schtasks /delete /tn "TileIQ nightly prices" /f`.

git will need to push without prompting. Either sign in once with GitHub Desktop or the GitHub CLI
(`gh auth login`), or use a credential-cached HTTPS remote, so the scheduled task isn't blocked
waiting for a password.

### Option B — Refresh in GitHub Actions (no PC required)

A runner starts clean, so it must do a **full** refresh. Private repos get 2,000 free Actions minutes
a month; a weekly full refresh uses roughly 150 minutes per run, about **600 a month** — inside the
quota. Do not schedule a full refresh nightly; that would be ~4,500 minutes and would be billed.

Create `.github/workflows/refresh.yml`:

```yaml
name: Weekly refresh
on:
  schedule:
    - cron: "30 19 * * 6"     # Sunday 01:00 Sri Lanka time
  workflow_dispatch:           # also lets you run it by hand
jobs:
  refresh:
    runs-on: ubuntu-latest
    timeout-minutes: 300
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r requirements.txt
      - run: python -m tileiq.pipeline --refresh
      - run: |
          git config user.name "tileiq-bot"
          git config user.email "bot@users.noreply.github.com"
          git add -A site
          git commit -m "weekly refresh" || echo "nothing changed"
          git push
```

Then: repo **Settings** → **Actions** → **General** → **Workflow permissions** → select
**Read and write permissions** → Save. Otherwise the bot cannot push.

Run it once by hand first: **Actions** tab → *Weekly refresh* → **Run workflow**.

### Option C — No hosting at all

For a laptop demo or a machine on the office network:

```bash
python -m http.server 8765 --directory site
```

Share `http://<your-ip>:8765` on the LAN. Nothing leaves the building.

---

## Part 4 — Verify after every deployment (60 seconds)

1. Open the site. **Overview** should load in about a second.
2. Left rail, bottom: the **build time** should be recent.
3. **Price audit** page → *Live spot check* should read something like `8/8 matched on last run`.
   Anything else means a source site changed its layout and a scraper needs attention.
4. **Sources** page → every source should show a sensible product count (Rocell ~800,
   Macktiles ~565, Lanka Tiles ~321, global ~1,800).
5. **Marketing** page → the brand table should show follower numbers, not blanks. LinkedIn
   throttles heavy use; occasional blanks are normal and fill in on the next refresh.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Page loads but all numbers are stale | Browser cached the old JSON | Rebuilds change the asset URLs automatically; hard-refresh once with Ctrl+Shift+R |
| Blank page, console shows `fetch` errors | Opened via `file://` | Serve it over HTTP (Part 1.1) or use the deployed URL |
| Cloudflare build fails | A build command was entered | It must be empty, with output directory `site` |
| Push rejected, file too large | A cache folder got committed | Confirm `.gitignore` lists `data/raw/`, `data/processed/`, `data/images/` |
| Spot check reports "price changed" | The source genuinely changed its price | Normal — the next refresh picks it up |
| Spot check reports "failed" or "no product found" | A source site changed its HTML | The scraper for that source needs updating |
| Marketing page missing YouTube numbers | YouTube rate-limited the request | Re-run the refresh; the value returns |

---

## What it costs

| Item | Cost |
|---|---|
| Cloudflare Pages hosting and bandwidth | free |
| Cloudflare Access, up to 50 users | free |
| GitHub private repository | free |
| GitHub Actions weekly refresh | free within the 2,000 min/month quota |
| Custom domain | only the domain registration, if you want a new one |

The only reason to pay anything later is a small always-on VM (about $5/month) if you want refreshes
to run without depending on an office PC.
