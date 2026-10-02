# Deploying TileIQ — comprehensive guide

TileIQ's interface is a **static site**: HTML, CSS, JavaScript, JSON and images. Nothing to run on a
server, nothing to pay for. Everything below is free.

**What gets deployed:** the `site/` folder only — ~68 MB, 3,490 tile thumbnails, ~1.8 MB of data and
~100 KB of code. A packaged `site.zip` (60 MB) sits in the project root for drag-and-drop uploads.

**Never deployed or committed:** `data/raw/` (1.1 GB page cache), `data/processed/` (working files),
`data/images/` (local thumbnail cache). `.gitignore` already excludes them.

---

## First: fix the error you just hit

```
fatal: unable to access 'https://github.com/<your-account>/tileiq.git/': error 400
```

The remote was saved with the literal placeholder `<your-account>` instead of your GitHub username.
Your commit is fine; only the remote address is wrong. Fix it with your real username:

```bash
git remote set-url origin https://github.com/YOUR-USERNAME/tileiq.git
```

Check it took:

```bash
git remote -v
```

Or, if you would rather not use GitHub at all, remove it and use Option A below:

```bash
git remote remove origin
```

---

## Which option should you pick?

| | Option A — Direct upload | Option B — GitHub + Cloudflare | Option C — Netlify Drop | Option D — Local / LAN |
|---|---|---|---|---|
| **Time to live** | ~10 min | ~25 min | ~5 min | 1 min |
| **Needs GitHub** | No | Yes | No | No |
| **Private to your team** | Yes, free | Yes, free | No (paid feature) | Yes, office only |
| **Updates** | Re-upload the folder | `git push`, deploys itself | Re-drag the folder | Re-run the pipeline |
| **Best for** | Getting it in front of leadership this week | The long-term setup | A quick throwaway demo | Keeping it inside the building |

**Recommendation:** start with **Option A** to get it live and shareable today, then move to
**Option B** when you want refreshes to publish themselves.

---

## Option A — Cloudflare Pages, direct upload (no GitHub)

### A1. Create the account
Sign up free at **dash.cloudflare.com** (email + password, no card).

### A2. Create the project
1. Left sidebar → **Workers & Pages**
2. **Create** → **Pages** tab → **Upload assets**
3. Project name: `tileiq` → **Create project**

### A3. Upload
Drag **`site.zip`** (in the project root, 60 MB) onto the upload area — or click *select from
computer* and pick the whole `site` folder.

> Upload the **contents** of `site`, not the folder itself. If you drag the folder and the site comes
> up blank, re-upload using `site.zip`, which has the correct structure built in.

Wait for the files to finish, then **Deploy site**. You get a URL like
`https://tileiq.pages.dev` within a minute.

### A4. Lock it to your team — do this before sharing the link
Until you do, anyone with the URL can read it.

1. Cloudflare dashboard → **Zero Trust** (left sidebar; accept the free plan if prompted)
2. **Access** → **Applications** → **Add an application** → **Self-hosted**
3. Application name: `TileIQ`. Domain: paste your `tileiq.pages.dev` hostname
4. **Add policy** → Policy name: `Vallibel One staff`, Action: **Allow**
5. **Include** → **Emails ending in** → `@vallibelone.com`
   (or choose **Emails** and list the leadership team one by one)
6. Save

Visitors now receive a one-time code by email before the site opens. Free for up to 50 users.

### A5. Updating later
After any rebuild:

```bash
python -m tileiq.pipeline
```
```bash
python -c "import shutil; shutil.make_archive('site','zip','site')"
```

Then Cloudflare → your project → **Create deployment** → upload the new `site.zip`. The previous
version stays available for rollback.

---

## Option B — GitHub + Cloudflare Pages (publishes itself)

### B1. Create the repository
On github.com: **New repository** → name `tileiq` → **Private** → do **not** add a README → Create.

> Keep it private. The source pages are public, but the analysis is not something to hand competitors.

### B2. Point the remote at it (with your real username)

```bash
git remote set-url origin https://github.com/YOUR-USERNAME/tileiq.git
```

If `git remote -v` prints nothing, add it instead:

```bash
git remote add origin https://github.com/YOUR-USERNAME/tileiq.git
```

### B3. Push

```bash
git branch -M main
```
```bash
git push -u origin main
```

**On authentication:** GitHub rejects account passwords. When the credential window appears, choose
**Sign in with your browser** — Git Credential Manager ships with Git for Windows and stores it.
If you are asked for a password in the terminal instead, generate a token at
github.com → Settings → Developer settings → **Personal access tokens (classic)** → Generate new
token → scope **repo** → use that token as the password.

The first push uploads ~68 MB and takes a few minutes.

### B4. Connect Cloudflare
1. dash.cloudflare.com → **Workers & Pages** → **Create** → **Pages** → **Connect to Git**
2. Authorise GitHub, pick `tileiq`
3. Build settings — the screen most people get wrong:
   - **Framework preset:** `None`
   - **Build command:** *leave completely empty*
   - **Build output directory:** `site`
4. **Save and Deploy**

### B5. Lock it down
Same as **A4** above.

### B6. Updating later
```bash
python -m tileiq.pipeline
```
```bash
git add -A && git commit -m "refresh" && git push
```
Cloudflare redeploys automatically, usually within two minutes.

---

## Option C — Netlify Drop (fastest, but public)

1. Open **app.netlify.com/drop**
2. Drag the `site` folder onto the page
3. You get a live URL in seconds

No account needed to start, but **password protection is a paid feature on Netlify**, so treat any
link as public. Fine for a throwaway demo, not for leadership material.

---

## Option D — No hosting at all

For a laptop demo or a machine on the office network:

```bash
python -m http.server 8765 --directory site
```

Open `http://localhost:8765`, or share `http://<your-ip>:8765` on the office LAN. Nothing leaves the
building.

> The site must be served over HTTP. Opening `site/index.html` by double-clicking shows a blank page,
> because browsers block `fetch()` on `file://` URLs.

---

## Custom domain (optional, free on Cloudflare)

If a company domain is already on Cloudflare: Pages → your project → **Custom domains** → **Set up a
domain** → `tileiq.vallibelone.com`. The certificate is issued automatically. If the domain is
elsewhere, Cloudflare shows the exact CNAME record to add at your registrar.

---

## Keeping the data fresh

| Command | Re-fetches | Time | Works on a clean clone? |
|---|---|---|---|
| `python -m tileiq.pipeline` | nothing — rebuilds from the local cache | ~2 min | No |
| `python -m tileiq.pipeline --refresh-prices` | only sources that publish prices | ~10 min | No |
| `python -m tileiq.pipeline --refresh` | every catalogue, global benchmark and marketing | 2–3 hrs | Yes |

**The catch:** the first two rebuild from `data/raw/`, which is not in the repository because it is
1.1 GB. They only work on the machine that holds the cache — the PC where the project was built. A
clean clone or a cloud runner must use `--refresh`.

### Scheduling it on the office PC (works with Option A or B)

Open a terminal **in the project folder** and run once:

```bash
schtasks /create /tn "TileIQ nightly prices" /tr "cmd /c cd /d \"%CD%\" && python -m tileiq.pipeline --refresh-prices" /sc daily /st 02:00 /rl highest
```

```bash
schtasks /create /tn "TileIQ weekly full refresh" /tr "cmd /c cd /d \"%CD%\" && python -m tileiq.pipeline --refresh" /sc weekly /d SUN /st 01:00 /rl highest
```

With **Option B**, append the push so it publishes itself:

```bash
schtasks /create /tn "TileIQ nightly publish" /tr "cmd /c cd /d \"%CD%\" && python -m tileiq.pipeline --refresh-prices && git add -A && git commit -m \"nightly refresh\" && git push" /sc daily /st 02:00 /rl highest
```

Check: `schtasks /query /tn "TileIQ nightly prices"` · Remove: `schtasks /delete /tn "TileIQ nightly prices" /f`

### Or refresh in GitHub Actions (Option B only)

A runner starts clean, so it must do a **full** refresh. Private repos get 2,000 free minutes a
month; a weekly full refresh is ~150 minutes per run, about 600 a month — inside the quota. A
*nightly* full refresh would be ~4,500 minutes and would be billed, so keep it weekly.

`.github/workflows/refresh.yml`:

```yaml
name: Weekly refresh
on:
  schedule:
    - cron: "30 19 * * 6"     # Sunday 01:00 Sri Lanka time
  workflow_dispatch:
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

Then repo **Settings** → **Actions** → **General** → **Workflow permissions** → **Read and write
permissions** → Save. Run it once by hand from the **Actions** tab to confirm.

---

## Verify after every deployment (60 seconds)

1. Open the site — the **Overview** should appear in about a second
2. Bottom of the left rail: the **build time** should be recent
3. **Price audit** → *Live spot check* should read something like `10/10 matched`.
   A "price changed" row is normal; "failed" means a source changed its layout
4. **Sources** → sensible counts: Rocell ~800, Macktiles ~565, Lanka Tiles ~321, global ~1,800
5. **Marketing** → follower numbers present. Occasional blanks mean LinkedIn or YouTube
   rate-limited that request; they return on the next refresh

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `error 400` on push | The remote still contains `<your-account>` | `git remote set-url origin https://github.com/YOUR-USERNAME/tileiq.git` |
| `Repository not found` | Repo not created, or no access | Create it on github.com first; confirm the name matches exactly |
| `Authentication failed` | GitHub no longer accepts passwords | Sign in through the browser prompt, or use a personal access token (B3) |
| `support for password authentication was removed` | Same as above | Same as above |
| Deployed site is blank | Uploaded the folder instead of its contents | Re-upload `site.zip` |
| Blank page locally, console shows `fetch` errors | Opened via `file://` | Serve over HTTP (Option D) |
| Cloudflare build fails | A build command was entered | Clear it; output directory must be `site` |
| Numbers look stale after a refresh | Browser cache | Rebuilds change the asset URLs automatically; hard-refresh once with Ctrl+Shift+R |
| Push rejected, file too large | A cache folder got committed | Confirm `.gitignore` lists `data/raw/`, `data/processed/`, `data/images/`, `site.zip` |

---

## What it costs

| Item | Cost |
|---|---|
| Cloudflare Pages hosting and bandwidth | free |
| Cloudflare Access, up to 50 users | free |
| GitHub private repository | free |
| GitHub Actions weekly refresh | free within 2,000 min/month |
| Custom domain | only the registration, if you want a new one |
| **Total** | **LKR 0 per month** |

The only reason to pay later is a small always-on VM (~$5/month) if you want refreshes to run
without depending on an office PC being switched on.
