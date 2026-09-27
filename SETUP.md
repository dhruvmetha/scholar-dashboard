# Setting up your own Scholar Dashboard

This guide takes you from a fork of this repo to a working copy of everything:

- the dashboard website, hosted free on GitHub Pages;
- weekly paper digests that Claude builds from your Google Scholar alert emails and from a web survey;
- encrypted notes, highlights and Apple Pencil ink on papers, synced through your repo;
- the **Chat** tab, where Claude Code on your Mac discusses the paper you're reading;
- optionally, chat from an iPad or iPhone (through Tailscale), and a local copy of the site.

Plan on about an hour. Steps 1–5 give you the website; 6–8 add digests and notes; 9–10 add chat.

---

## How the pieces fit

```
                        GitHub repo (your fork)
      papers / interests / groups CSVs, index.html, annotations/ (encrypted notes)
         │  GitHub Pages serves the site          ▲  the page saves your edits
         ▼                                        │  (read, starred, lists, notes) with your token
   Browser: the dashboard  ───────────────────────┘
         │  Chat tab
         ▼
   bridge/scholar_bridge.py on your Mac (127.0.0.1:7823)  ──►  claude -p  (Claude Code)
         ▲
         │  Tailscale (optional): the iPad reaches the bridge over your private network

   Digest runs (Claude, weekly): pull_from_github.sh → read alerts / search the web →
   update the CSVs → sync_to_github.sh (commits and pushes; the site updates)
```

Everything is a single `index.html` with no build step. The page reads the CSVs straight from GitHub on every load, so a digest push shows up on the next refresh.

## What you need

- A **GitHub** account.
- A **Mac**, for the chat bridge and the local-server scripts. The website itself works in any browser, and the digests can run from any machine with Claude.
- **Python 3** and **git** (`xcode-select --install` provides both).
- **Claude Code**, signed in with your Claude account, for chat and for running digests by hand.
- The **Claude desktop app**, if you want the digests to run on a schedule (step 8). It also needs the **Gmail connector**, for the email digest.
- **Google Scholar alerts** delivered to that Gmail address.
- Optional: **Tailscale**, for chat from an iPad or iPhone.
- **Chrome** on the Mac is the tested browser for the chat bridge. On the iPad, Safari works (see step 10).

---

## 1. Fork and clone

1. On GitHub, **fork** the repo. Keeping it a fork lets you pull later improvements (see *Getting updates* at the end). The repo must stay **public**: the page reads the CSVs without logging in, and free GitHub Pages needs a public repo. Your notes are still private, because they are encrypted in the browser before they're ever pushed.
2. Clone it:

```bash
git clone https://github.com/<your-username>/scholar-dashboard.git
cd scholar-dashboard
```

If you renamed the fork, use that name everywhere this guide says `scholar-dashboard`.

## 2. Start from clean data

The fork comes with Sumanth's papers, research interests and encrypted notes. Clear them out:

```bash
# Sumanth's encrypted notes, link-preview pages and old reports
git rm -r -q annotations p scholar_report_*.md weekly_survey_*.md

# keep only the header row of the papers database
head -1 papers_database.csv > /tmp/h && mv /tmp/h papers_database.csv
```

Then edit these three files by hand:

- **`interests_database.csv`**: your research interests, one row each. The columns are explained in `CLAUDE.md` under *Interests Database Schema*. Keep the header row. Mark the ones you care about `status=confirmed`. `relevance_mapping` (`definitely`, `probably` or `mildly`) decides how highly matching papers rank. You can add, approve and tune interests later in the dashboard's **Interests** tab.
- **`groups_database.csv`**: the topic groups the home page is organised by. Note that this file is **separated by `|`, not commas**. Keep the ones that suit you, rename or delete the rest, and set `display_order`.
- **`CLAUDE.md`**: the instructions Claude follows for digest runs. Rewrite the top sections (*Me*, *Research Interests*, *Preferences*) and the survey sources (the conferences, journals and arXiv search clusters) for your field. Keep the rest: the workflow, database schema, ID format and rules are what keep the data consistent. Replace `memory/context/research-interests.md` and `memory/glossary.md` with your own, or delete them.

## 3. Point the code at your repo and site

A handful of addresses are hard-coded. Set your values and run this from the repo folder (it's macOS `sed`; it was tested against the current files):

```bash
GH_USER=<your-github-username>
REPO=scholar-dashboard                       # your fork's name
SITE="https://$GH_USER.github.io/$REPO/"     # where GitHub Pages will serve it (step 4)
ORIGIN="https://$GH_USER.github.io"          # the site's origin: no path, no trailing slash

sed -i '' "s#https://www.sumanthtangirala.com/scholar-dashboard/#$SITE#g" make_share_pages.py sync_to_github.sh
sed -i '' "s#sumanth-tangirala/scholar-dashboard#$GH_USER/$REPO#g" index.html pull_from_github.sh sync_to_github.sh
sed -i '' "s#const GH_OWNER  = 'sumanth-tangirala'#const GH_OWNER  = '$GH_USER'#; s#const GH_REPO   = 'scholar-dashboard'#const GH_REPO   = '$REPO'#" index.html
sed -i '' "s#{'https://www.sumanthtangirala.com', 'https://sumanthtangirala.com', #{'$ORIGIN', #" bridge/scholar_bridge.py
sed -i '' "s#Origin: https://www.sumanthtangirala.com#Origin: $ORIGIN#" bridge/install_bridge.sh
sed -i '' "s#<string>/Users/htnamus/All_Stuff/Programming_Stuff/ScholarDashboard</string>#<string>$PWD</string>#" com.scholar-dashboard.plist
```

What that changed:

| File | Setting | What it's for |
|---|---|---|
| `index.html` | `CSV_BASE_URL`, `GH_OWNER`, `GH_REPO` | where the page reads the databases and saves your edits and notes |
| `make_share_pages.py` | `SITE` | the address in link previews |
| `pull_from_github.sh`, `sync_to_github.sh` | the repo URL | what digest runs pull from and push to |
| `bridge/scholar_bridge.py` | `ORIGINS` | which websites may talk to the chat bridge |
| `bridge/install_bridge.sh` | health-check origin | the install script's final check |
| `com.scholar-dashboard.plist` | `WorkingDirectory` | the optional local server (step 11) |

Two edits by hand in `index.html`:

- near the top, `<meta name="description" ...>` mentions "Sumanth's research interests";
- in the top bar, `<a href="https://sumanthtangirala.com" ... class="nav-portfolio-link">Sumanth Tangirala</a>` is a link to your own homepage and name. Change both, or delete the link and the `nav-brand-sep` divider right after it.

Check nothing personal is left:

```bash
grep -rn -i "sumanth\|htnamus" --exclude-dir=.git . | grep -v "^./SETUP.md"
```

Commit and push:

```bash
python3 make_share_pages.py          # link-preview pages for your (still empty) database
git add -A && git commit -m "Set up my own Scholar Dashboard" && git push
```

## 4. Turn on GitHub Pages

On the repo on GitHub, go to **Settings → Pages → Build and deployment**:

- **Source:** Deploy from a branch
- **Branch:** `main`, folder `/ (root)`, then **Save**.

After a minute or two the site is at `https://<your-username>.github.io/scholar-dashboard/`. This is Sumanth's setup too (branch `main`, root folder); his address differs only because his user site has a custom domain.

- **Custom domain (optional):** if your `<username>.github.io` site has one, this project site appears under it automatically. If you use one, set `SITE` and `ORIGIN` in step 3 to that domain.
- **Updates are delayed:** Pages takes a minute or two to rebuild after each push, and browsers may cache the page for up to 10 minutes. The ↻ button in the top bar fetches the newest copy.

## 5. A GitHub token

The scripts and the page write to your repo with a **fine-grained personal access token**:

1. Go to https://github.com/settings/personal-access-tokens/new.
2. **Repository access:** Only select repositories → your fork.
3. **Permissions → Repository permissions → Contents:** Read and write. Nothing else is needed.
4. Pick an expiry you're comfortable with. When it expires, the steps below simply need a new one.

**For the scripts** (digest runs):

```bash
printf '%s' 'github_pat_...' > .github_token
chmod 600 .github_token
```

`.github_token` is in `.gitignore`. Never commit it, and never paste it anywhere but the two places in this guide.

**For the website**, in each browser you use, paste a token once:
- **Library → Connect GitHub**, so your read, starred, list and hidden changes save automatically;
- the notes password dialog (step 7), so your notes sync.

The token is stored only in that browser. You can reuse the same token or make one per device.

## 6. Google Scholar alerts

In Google Scholar, create alerts (the envelope icon on an author's profile, on a search, or on "cited by" pages) for the people and topics you follow, delivered to your Gmail. The email digest reads alerts from `scholaralerts-noreply@google.com` in the past week. The `notes` column records which alert group each paper came from, so name the groups in your `CLAUDE.md` *Preferences* if you like.

## 7. Encrypted notes

1. Open any paper, press **Read**, then open the **Notes** panel.
2. Choose **Set a notes password**, paste your GitHub token, and choose a password.

This creates `annotations/_vault.json` in your repo. Your notes, highlights, comments and ink are encrypted in the browser (AES-256-GCM, with the key derived from your password) before being pushed. The repo only ever holds ciphertext.

- **On another device:** paste a token and enter the **same password**.
- **Forgotten password:** there is no recovery, because the notes can't be decrypted without it.
- **The site's address matters:** encryption only runs on `https://` pages, which GitHub Pages is, or on `localhost` and `*.localhost` addresses. A plain `http://` address other than those will say notes need a secure address.
- **Never edit or delete files in `annotations/` by hand.** Digest runs are told the same thing in `CLAUDE.md`.

## 8. Weekly digests

A digest run is Claude following the *Execution Workflow* in `CLAUDE.md`:

1. pull the latest databases;
2. find papers, either from your Scholar alert emails (**Mode 1**) or from a survey of conferences, journals and arXiv (**Mode 2**);
3. deduplicate them and score them against your interests;
4. fetch real abstracts;
5. update the CSVs;
6. push.

Refresh the site afterwards to see the new papers.

**Scheduled, in the Claude desktop app** (this is how Sumanth runs them):

1. In Claude desktop, connect the **Gmail** connector (Settings → Connectors). Mode 1 needs it.
2. Create two **scheduled tasks** that work in your repo folder, for example weekly on Monday morning:

   - **Email digest (Mode 1)**:
     > In the Scholar Dashboard folder, run **Mode 1 (Google Scholar email digest)** exactly as `CLAUDE.md` describes, for Google Scholar alert emails (`from:scholaralerts-noreply@google.com`) from the past 7 days. Step 0 is `bash pull_from_github.sh`: if it fails, stop and tell me. Finish with `bash sync_to_github.sh`, then give me a short summary of what was added.
   - **Web survey (Mode 2)**:
     > In the Scholar Dashboard folder, run **Mode 2 (weekly web survey)** exactly as `CLAUDE.md` describes, for papers from the last 1–3 months. Step 0 is `bash pull_from_github.sh`: if it fails, stop and tell me. Finish with `bash sync_to_github.sh`, then give me a short summary.

3. Run each once by hand to approve the tools it needs: git, python3, bash, web search, Gmail.

**By hand, in Claude Code:** `cd` into the repo, run `claude`, and paste either prompt. Mode 1 needs your Gmail connected to Claude Code; Mode 2 needs only web search.

The first run on an empty database takes a while, and it's worth reading its output. After a couple of runs, approve or dismiss the interests and groups Claude suggests in the **Interests** tab.

## 9. Chat with Claude about a paper

The **Chat** tab talks to a small server on your Mac, `bridge/scholar_bridge.py`. It runs Claude Code (`claude -p`) with one conversation per paper and streams replies back to the page.

1. **Install Claude Code and sign in** (see https://docs.claude.com/en/docs/claude-code for other install options):

   ```bash
   curl -fsSL https://claude.ai/install.sh | bash
   claude            # sign in once, then /exit
   claude -p "Say hi" # should print a reply
   ```

   Keep it up to date (`claude update`): the bridge relies on current command-line options.

2. **Install the bridge.** It starts now and at every login:

   ```bash
   bash bridge/install_bridge.sh
   ```

   It should end with `Bridge running.` Logs are in `/tmp/scholar-bridge.log` and `/tmp/scholar-bridge.err`.

3. **Pair your browser.** In **Chrome on the Mac**, open your site, open a paper and go to the **Chat** tab. Press **Connect to Claude Code**; if Chrome asks to allow access to devices on your local network, allow it. A macOS dialog appears showing a code: check it matches the one on the page and click **Allow**. The page then remembers the pairing.

How it's kept safe:
- The bridge listens only on 127.0.0.1.
- It answers only the origins in `ORIGINS` (step 3).
- Every request needs the pairing token, and a token is only issued after you click Allow on the Mac.
- Claude runs with no shell and no plugins. It can read files only in `~/.scholar-bridge/work`, and can search and fetch the web.

Where things are kept:
- Chats, the token and cached PDFs are in `~/.scholar-bridge/`, never in the repo.
- Claude Code keeps its transcripts in `~/.claude/projects/`, unencrypted, on your Mac only.

With each message the page sends your decrypted notes on that paper and your research interests, so Claude can use them.

Usage counts against your own Claude plan, the same as using Claude Code directly. The chat's model menu offers Opus, Sonnet and Haiku.

Uninstall: `launchctl bootout gui/$(id -u)/com.scholar-dashboard.bridge && rm ~/Library/LaunchAgents/com.scholar-dashboard.bridge.plist`.

## 10. Chat from an iPad or iPhone (optional)

The iPad can't reach 127.0.0.1 on your Mac. Tailscale gives it a private HTTPS address instead:

1. Install **Tailscale** on the Mac (https://tailscale.com/download) and on the iPad (App Store), and sign in to the **same account** on both.
2. In the Tailscale admin console, on the **DNS** page, turn on **MagicDNS** and **HTTPS certificates**.
3. On the Mac, run:

   ```bash
   bash bridge/tailscale_setup.sh
   ```

   It prints an address like `https://your-mac.tailnet-name.ts.net`.
4. On the iPad, open a paper, go to the **Chat** tab, enter that address, then click **Allow** in the dialog on the Mac.

Only devices signed in to your Tailscale account can reach that address, and each one still has to be paired. **The Mac must be awake** for chat to work from the iPad.

Undo: `tailscale serve --https=443 off`.

**Home Screen app:** in Safari on the iPad or iPhone, open your site, then **Share → Add to Home Screen**. It opens full screen like an app. Use the ↻ button in the top bar to refresh it.

## 11. A local copy at `http://scholar.localhost` (optional)

This is useful for trying changes before you push. It runs a small web server from your repo folder at every boot, and needs `sudo` for port 80 and `/etc/hosts`:

```bash
./install_server.sh      # uninstall: ./uninstall_server.sh
```

Then open http://scholar.localhost. Use exactly that address, because notes need it (see step 7). The local page still reads the databases from GitHub, and falls back to the local files when offline. For a quick one-off without installing anything, run `./serve.sh` instead (http://localhost:8739).

## 12. Link previews

When you share a paper's link in a chat app, the preview shows its title, authors and venue. `sync_to_github.sh` regenerates the small `p/<id>/` pages behind this on every push, using `SITE` from step 3. There's nothing to do beyond step 3.

---

## Troubleshooting

- **The site is empty.** The database really is empty until the first digest runs. Also check that `CSV_BASE_URL` in `index.html` points at your repo, and open that URL plus `papers_database.csv` in a browser to confirm it loads.
- **Changes don't save** (the Library header says they stay in this browser):
  - reconnect GitHub with a valid token;
  - check the token has Contents read and write access to this repo and hasn't expired;
  - check `GH_OWNER` and `GH_REPO` in `index.html`.
- **Chat says it can't reach Claude Code.** On the Mac, run:

  ```bash
  curl -s -H "Origin: https://<your-username>.github.io" http://127.0.0.1:7823/health
  ```

  - `{"ok": true, ...}` means the bridge is fine; pair again from the Chat tab.
  - `{"error": "origin"}` means `ORIGINS` doesn't match your site's address exactly: scheme and host, no path.
  - No answer means the bridge isn't running: run `bash bridge/install_bridge.sh` again and read `/tmp/scholar-bridge.err`.
- **Chat starts but replies fail.** Run `claude -p "hi"` in Terminal. If that fails, sign in again or update Claude Code.
- **iPad chat stopped working:**
  - is the Mac awake?
  - is Tailscale connected on both devices?
  - does `tailscale serve status` on the Mac still show the address?
- **A digest run fails at step 0:** `.github_token` is missing or expired, or the remote URL in `pull_from_github.sh` is wrong.
- **You see an old version of the site:** use the ↻ button, or wait a few minutes for Pages and the browser cache.

## Getting updates from the original

To pull later improvements:

```bash
git remote add upstream https://github.com/sumanth-tangirala/scholar-dashboard.git   # once
git fetch upstream
git merge upstream/main
```

Keep **your** version of the data and anything personal: the three CSVs, `annotations/`, `p/` and `CLAUDE.md`'s top sections. If a merge conflicts there, take yours (`git checkout --ours <file>`). Code files like `index.html` and `bridge/` merge normally. Afterwards, re-run the step 3 commands and the check `grep` for any new hard-coded addresses.
