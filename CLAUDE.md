# Memory

## Me
Sumanth, robotics researcher. Current focus: data-driven verification of black-box robotic systems with black-box controllers.

## Research Interests

**Source of truth: `interests_database.csv`** — This CSV is the authoritative, dynamic record of all research interests. Both scheduled tasks (Mode 1 and Mode 2) read this file at the start of each run to determine what to search for and how to filter/rank papers. Do NOT hardcode interest lists in prompts or rely on memory files for filtering — always read this CSV.

→ Static reference (for human reading): memory/context/research-interests.md

## Preferences
- Email source: Google Scholar alerts
- Wants papers prioritized/filtered by interests above
- Remove duplicates across alerts
- Group papers thematically
- Maintain a database (CSV) of processed papers
- Final presentation: static website (dark mode, Google News-style grouped cards)

---

# Working Modes

This project operates in two modes. Both share the same deduplication, filtering, grouping, and database update steps — they differ only in how papers are sourced.

Both modes write to a **single unified database** (`papers_database.csv`). The `source_mode` column tracks provenance and can be:
- `"email"` — found via Google Scholar alerts only
- `"web_survey"` — found via web survey only
- `"email,web_survey"` — found by both (prefer email as primary source)
- `"manual"` — added by the user by hand (dashboard Library → + Add paper, or `/add-paper` here). Digest runs treat these like any other row (dedupe against them; if a digest finds the same paper, keep `manual` and don't add a copy).

## Adding a paper by hand
Library → **+ Add paper** (any paired device, through the bridge) or `/add-paper` in Claude Code on the laptop. Both follow `bridge/add_paper.md` for the research, and `bridge/add_paper.py` does the checking and publishing from the bridge's own copy of the repo (`~/.scholar-bridge/repo`), never from this working copy. A paper with no public version is never added (Library → To review keeps it private instead).

## Mode 1: Google Scholar Email Digest
- Read Google Scholar alert emails from Gmail
- Extract paper titles, authors, links
- **CRITICAL: Every paper MUST have a URL.** Google Scholar alert emails contain links for each paper — extract them. If a link is missing from the email, search for the paper on Google Scholar or arXiv to find it. Never leave the `url` column empty.
- Generate a **headline takeaway** for each paper (stored in DB)
- Deduplicate, filter, group, and present
## Mode 2: Weekly Web Survey
- Systematically search the sources below for papers from the last 1–3 months
- Follow the search methodology defined in this document
- **CRITICAL: Every paper MUST have a URL.** Always include the direct link (arXiv, DOI, conference page, etc.). Never leave the `url` column empty.
- Generate a **headline takeaway** for each paper (stored in DB)
- Deduplicate against existing DB entries; if a paper already exists from email, update `source_mode` to `"email,web_survey"` (don't create a duplicate)

## URL rule: store permanent, year-specific links (both modes)
- Some conference sites always show the *next* edition at their unversioned address, so those links break once the next year's site goes live. **RSS** is one: never store `https://roboticsconference.org/program/papers/{N}/`; always store the year-specific `https://roboticsconference.org/{YEAR}/program/papers/{N}/` (e.g. `/2026/` for RSS 2026). Apply the same idea to any conference site with a year-less program path.
- Prefer permanent identifiers when one exists: arXiv abstract page, DOI, OpenReview forum.
- Before saving a conference-page URL, check that it resolves (no 404) and shows the paper's title.

## Website / UI

The website (`index.html`) has three tabs:
- **"Recent Works"** (default): shows ALL papers in the database
- **"Email Digest"**: shows only papers where `source_mode` contains `"email"`
- **"Interests"**: shows all interests from `interests_database.csv`, grouped by category (Application Areas / Methods). Suggested interests show Approve/Dismiss buttons. When the user clicks a button, the status updates in-memory and a "Save CSV" button appears to download the updated file for replacement.

Papers appear in both paper tabs if their `source_mode` is `"email,web_survey"`.

The website dynamically reads `papers_database.csv` and `interests_database.csv` using PapaParse at load time. No build step is needed — just update the CSVs and refresh the page. All three files must be in the same folder.

### GitHub Sync Scripts

Two scripts manage the canonical database state on GitHub:

- **`pull_from_github.sh`** — Fetches the latest `papers_database.csv`, `interests_database.csv`, and `groups_database.csv` from GitHub and updates local files if the remote is newer. Uses HTTPS + `.github_token`. Run at the **start** of every task (Step 0) to avoid working with stale data. Exits non-zero on failure.
- **`sync_to_github.sh`** — Commits and pushes the updated CSVs (and `index.html`) to GitHub after a run completes. Run at the **end** of every task (Step 10). Requires `.github_token` file in the project directory.

The token file (`.github_token`) is gitignored and must be present locally for both scripts to work.

### Serving

A `launchd` daemon (`com.scholar-dashboard.plist`) runs `python3 -m http.server 80` bound to localhost from this folder. It starts on boot and auto-restarts if it crashes. `/etc/hosts` maps `scholar.localhost` (and the older `scholar.local`) to `127.0.0.1`.

- **URL**: `http://scholar.localhost`. Use this rather than `scholar.local`: browsers only allow the Web Crypto API that the encrypted notes use on https or `*.localhost` addresses.
- **Install**: `./install_server.sh` (one-time, requires sudo for hosts + port forward)
- **Uninstall**: `./uninstall_server.sh`
- **Logs**: `/tmp/scholar-dashboard.log`, `/tmp/scholar-dashboard.err`

---

# Web Survey — Sources & Methodology

## Tier 1: Robotics Conferences (check for accepted/published paper lists)

| Conference | Typical Timeline | What to Check |
|------------|-----------------|---------------|
| **ICRA** | Acceptances ~Jan–Mar, conference ~May | Accepted paper list, proceedings |
| **IROS** | Conference ~Oct, proceedings after | Recent proceedings |
| **RSS** | Conference ~Jul, acceptances ~Apr | Accepted paper list |
| **CoRL** | Conference ~Nov, proceedings after | Recent proceedings |

## Tier 2: ML Conferences (robotics-relevant papers only)

| Conference | Typical Timeline | What to Check |
|------------|-----------------|---------------|
| **NeurIPS** | Conference ~Dec, proceedings after | Recent proceedings, robot/control track |
| **ICML** | Acceptances ~Apr, conference ~Jul | Accepted paper list |
| **ICLR** | Conference ~May, acceptances ~Jan | Accepted paper list |
| **L4DC** | Conference ~Jun | Accepted paper list |

Focus on: robotics applications, control theory + learning, safety/verification, diffusion/flow models for control, conformal prediction.

## Tier 2.5: Workshops (venues vary year to year)

Workshops are held alongside major conferences or independently. They change every year, so there is no fixed list of venues. Instead, when running a web survey:

1. **Search for recent workshops** by querying for workshops co-located with the Tier 1 and Tier 2 conferences above (e.g., "ICRA 2026 workshops", "NeurIPS 2025 workshops")
2. **Filter by topic relevance** — look for workshops whose titles/themes overlap with the research interests (verification, safe learning, diffusion policies, conformal prediction, foundation models for robotics, etc.)
3. **Check workshop proceedings/websites** for accepted papers or contributed talks

Examples of recurring workshop themes to watch for (names and exact venues change):
- Safe robot learning / safety in learning-based control
- Diffusion models for decision-making / planning
- Foundation models for robotics
- Formal methods meets learning
- Distribution-free uncertainty quantification
- Data-driven control and verification

Since workshops are inherently ephemeral, don't maintain a fixed list — discover them fresh each survey cycle.

## Tier 3: Journals (recent issues, rolling publications)

| Journal | Abbreviation | Notes |
|---------|-------------|-------|
| **IEEE Robotics and Automation Letters** | RA-L | Rolling, bimonthly |
| **International Journal of Robotics Research** | IJRR | Monthly |
| **IEEE Transactions on Robotics** | T-RO | Bimonthly |
| **Transactions on Robot Learning** | T-RL | Newer venue |

## Tier 4: Arxiv (preprints, most up-to-date)

Run targeted searches grouped by research interest:

### Search Clusters

| Cluster | Search Keywords |
|---------|----------------|
| **Verification & safety** | "data-driven verification" robot, "black-box verification" control, reachability learned systems, safety guarantees robot |
| **Conformal prediction + robotics** | conformal prediction robot, distribution-free guarantees control, conformal prediction planning |
| **Visuomotor policy verification** | verification visuomotor policy, certifying vision-based control, testing neural robot policy |
| **Diffusion / flow matching policies** | diffusion policy robot, flow matching imitation learning, diffusion model manipulation |
| **Generalist robot policies** | generalist robot policy, foundation model robotics manipulation, multi-task robot learning |
| **Controller composition** | composing controllers robot, modular policy composition, skill composition robot |
| **Active learning for robotics** | active learning robot verification, sample-efficient robot, active learning control |
| **Imitation & reinforcement learning** | imitation learning manipulation 2026, reinforcement learning locomotion 2026 |

---

# Execution Workflow (both modes)

0. **Pull from GitHub** — **ALWAYS the first step.** Run `bash pull_from_github.sh` from the project directory. This fetches the latest `papers_database.csv` and `interests_database.csv` from GitHub, ensuring the task starts with up-to-date data regardless of what previous sessions pushed. If this script exits non-zero, **abort immediately** and notify the user — do not proceed with stale or missing data.
0.5. **Tag approved topics' existing papers** — `python3 bridge/add_topic.py --pending` lists confirmed topics whose existing papers were never tagged (the user just approved or created them). For each: decide from its `description` which papers belong (see `bridge/add_topic.md`), write `{"ids": [...]}` to a temp file, run `python3 bridge/add_topic.py "<topic>" --ids <file>` (it applies and publishes from its own copy of the repo), then re-run `bash pull_from_github.sh`.
1. **Load interests** — Read `interests_database.csv` as the sole source of truth for filtering, ranking, and search query construction. Use confirmed interests (status="confirmed") for active filtering; use their `relevance_mapping` column for tier assignment. Ignore rejected interests. Treat suggested interests as "mildly" relevant.
2. **Source** — Gather raw paper list (from emails or web sources above)
3. **Deduplicate** — Remove papers already in the database or appearing multiple times. If a paper exists from a different source, update `source_mode` to reflect both sources. **Match on the paper itself, never on the generated `id`**: the same paper gets a different slug when the author or title words are parsed differently (e.g. `wan-2026-free-checker` vs `wan-2026-no-free`). Treat a paper as already present if its arXiv ID / DOI / OpenReview ID matches, or its title matches after lowercasing and stripping punctuation. Rows with `is_hidden="true"` count as present: the user hid them, so never add them again.
4. **Filter & score** — For each paper, determine which confirmed interests from `interests_database.csv` it matches and record them in `matched_interests` (pipe-separated, exact `interest_name` values). Assign a `residual_score` (integer, typically -1, 0, or +1) to fine-tune relevance beyond what the interests alone capture. The website computes dynamic relevance as: `max(matched interest relevance_mapping scores) + residual_score`, clamped to [1,3] and mapped to definitely/probably/mildly. Also set the static `relevance_tier` column as a snapshot fallback.
5. **Group** — Assign `theme_groups` (pipe-separated) to each paper using the live canonical list from `groups_database.csv` (confirmed entries only, sorted by `display_order`). Default to 1–2 groups; add a third only when the paper makes a genuine, substantial contribution to a third cluster. Hard cap: 5.
   - **If a paper fits an existing confirmed group**, use its exact `group_name` from `groups_database.csv`.
   - **If a paper is genuinely novel and fits no existing group**, create a new row in `groups_database.csv` with `status="suggested"` and a descriptive `group_name`. Assign that group name to the paper. The user will review it in the Interests tab of the website (Approve to confirm, Dismiss to reject).
   - **NEVER use `"Other"` as a theme_group value — under any circumstances.** `"Other"` is not a valid group and is not in `groups_database.csv`. If a paper does not fit any existing confirmed group AND is not worth proposing a new group for (i.e., it's low-relevance or off-topic), leave `theme_groups` **empty** instead. Never fall back to `"Other"`, `"Misc"`, `"Uncategorized"`, or similar dumping-ground labels.
   - **Never invent group name variants** (e.g., "Safe RL", "Diffusion Policies", "Verification & Safety" are all wrong). Use exact `group_name` values from `groups_database.csv`.
   - Current confirmed groups (as of last sync — always re-read from CSV): `Safety & Verification`, `Conformal Prediction`, `Diffusion & Flow Policies`, `VLA & Generalist Policies`, `Visuomotor Policies`, `Imitation Learning`, `Reinforcement Learning`, `Controller Composition`, `Formal Methods & STL`, `Active Learning`, `Planning & Control`, `World Models`.
   - `Visuomotor Policies`: policies that act from camera/visual input, VLAs included, and papers that propose, train, analyse, test, monitor or verify them.
6. **Fetch metadata & abstract** — For each new paper, visit the paper page (arXiv, conference site, etc.) to extract the **exact title**, **full author list**, **publication date/year**, and **actual abstract** (verbatim, 100-300 words). Store the abstract in the `abstract` column. Do NOT generate or paraphrase the abstract — it must be the real text from the paper. Also set `pdf_url` (see the schema): the arXiv PDF when there is one (search arXiv by exact title for non-arXiv papers), else an open PDF from a host that allows cross-site loading, else leave it empty.
7. **Generate headline & summary** — From the title + abstract, generate: (a) a concise ~10-15 word headline takeaway for the `headline` column, and (b) a 3-4 sentence summary of the contribution/approach/result for the `summary` column.
8. **Discover new interests** — Identify recurring themes/methods in papers that don't match any existing interest in the database. Add as "suggested" entries to `interests_database.csv` (see Interest Discovery below).
8b. **Suggest new topics** — the same for topics (see Group Discovery Rules): a recurring theme no confirmed topic captures well enough to browse by, with 3+ papers in the database that would belong. Suggested topics get no papers until the user approves them; approving tags the existing papers.
9. **Assign IDs & update databases** — For each new paper, generate a unique `id` using the **Paper ID Format** rules (see below): `{lastname}-{year}-{keyword1}-{keyword2}`, with `-2`/`-3` suffixes for collisions. The `id` must be set before writing the row. Append new papers to `papers_database.csv` (with `id` as the first column) and new suggested interests to `interests_database.csv`. **Write with the file's own header** (read the fieldnames from the CSV); never hardcode a column list, because the dashboard adds columns (`pdf_url`, `is_hidden`, `user_notes`) and a fixed list would drop them. Leave columns you don't set empty, and make sure the file ends with a line break before appending.
10. **Sync to GitHub** — Run `bash sync_to_github.sh` to commit and push the updated databases back to GitHub. This is the canonical publish step.
11. **Present** — Share the updated website link with user. If new interests were suggested, mention the Interests tab.

---

# Database Schema

Maintain a CSV file (`papers_database.csv`) with these columns:

| Column | Description |
|--------|-------------|
| `id` | Unique paper ID — see **Paper ID Format** section below. **Always the first column.** |
| `title` | Paper title (use the exact title from the paper, not a paraphrase) |
| `authors` | Author list (extract from the paper page; use "not specified" only as last resort) |
| `venue` | Conference/journal/arxiv |
| `publishing_date` | Publication month and year, e.g. "Mar 2026". Extract from arXiv ID (YYMM), conference date, or journal issue. Fall back to year only if month unknown. |
| `url` | Link to paper |
| `date_found` | Date this paper was added |
| `source_mode` | "email", "web_survey", "email,web_survey", or "manual" (added by hand) |
| `relevance_tier` | **Static fallback only.** "definitely", "probably", or "mildly". The website now computes relevance dynamically from `matched_interests` + `residual_score` (see below). This column is still written at ingestion time as a snapshot, but the website ignores it when `matched_interests` is populated. |
| `matched_interests` | Pipe-separated list of interest names from `interests_database.csv` that this paper matches (e.g. `"Conformal prediction\|Data-driven verification"`). **Must use exact `interest_name` values.** The website uses this + `residual_score` to compute dynamic relevance at render time. |
| `residual_score` | Integer adjustment to the interest-derived relevance score. Typically -1, 0, or +1. `+1` = paper is more relevant than its interests suggest (e.g., directly about data-driven verification of black-box systems, or combines multiple core interests). `-1` = paper is less relevant (e.g., pure theory with no robotics/learning connection). `0` = interest-based score is appropriate. The justification for any non-zero value MUST be noted in the `notes` column. |
| `theme_groups` | Pipe-separated list of thematic clusters (e.g. `"Safety & Verification\|Conformal Prediction"`). Typically 1–2 groups; up to 5 max for genuinely cross-cutting papers. **Always use canonical group names** — see Step 5 in the Execution Workflow. |
| `headline` | One-line attention-grabbing takeaway (generated, ~10-15 words). Shown as the main display text on the website. |
| `summary` | 3-4 sentence generated summary of the paper's contribution, approach, and key result. Shown on click in the website UI. |
| `abstract` | **The actual abstract from the paper** — fetch from arXiv, conference page, or publisher. Typically 100-300 words. Do NOT generate or paraphrase this; copy the real abstract verbatim. |
| `notes` | **Required triaging note** — always populate this field. Explain why the paper was selected and how it relates to your research interests. Use this format: for email papers, `"Alert: {researcher group(s)}. {Tier} — {one-line reason}"` (e.g., `"Alert: Lindemann/Tomlin. Core — data-driven verification + conformal prediction"`); for web survey papers, `"{Tier} — {one-line reason}"` (e.g., `"High — flow matching applied to visuomotor policy learning"`). Tier values: **Core** (definitely), **High** (probably), **Moderate** (probably/mildly boundary), **Low** (mildly). **If `residual_score` is non-zero**, append a justification: `" [residual +1: directly addresses black-box verification of learned controllers]"` or `" [residual -1: pure CBF theory, no data-driven component]"`. Never leave blank. |
| `is_read` | `"true"` or `"false"` — set by the user in the dashboard. **Never overwrite** when appending new papers; leave as `"false"` for new rows. |
| `is_starred` | `"true"` or `"false"` — set by the user in the dashboard. **Never overwrite** when appending new papers; leave as `"false"` for new rows. |
| `user_lists` | Pipe-separated (`\|`) list names the user has saved this paper to (e.g. `"reading-list\|important"`). **Never overwrite** when appending new papers; leave empty for new rows. |
| `pdf_url` | Direct link to an **open PDF the dashboard's reader can load** (it runs PDF.js in the browser, so the host must allow cross-site downloads). Fill it at ingestion: arXiv papers → `https://arxiv.org/pdf/{id}`; a non-arXiv paper that also has an arXiv version → that arXiv PDF; PMLR papers → the PDF linked from the proceedings page. Leave it empty for paywalled papers or hosts that block other sites (OpenReview, most publishers): the user can paste a link or drop in their own file from the dashboard. The user may also edit it; **never overwrite a non-empty value**. |
| `is_hidden` | `"true"` when the user hid the paper in the dashboard (it disappears from every view but stays in the CSV so it is never re-added). **Never overwrite**; leave empty for new rows. The column appears once the first paper is hidden. |

---

# Paper ID Format

Every paper in the database must have a unique `id` in the **first column**. IDs are human-readable slugs with a hierarchical tie-breaking scheme:

**Format:** `{lastname}-{year}-{keyword1}-{keyword2}`

| Component | Rules |
|-----------|-------|
| `lastname` | First author's last name, lowercase, ASCII-only, non-alphanumeric chars stripped. Use `unknown` if authors is "not specified". |
| `year` | 4-digit year extracted from `publishing_date` (e.g. `2026` from `"Mar 2026"`). |
| `keyword1`, `keyword2` | First 2 meaningful words from the title, after removing stop words (a, an, the, for, of, with, via, using, in, on, to, and, or, from, by, is, are, be, can, will, has, have, not, but, as, at, new, novel, etc.). Lowercase, ASCII-only. |
| **Tie-breaking** | If the base slug already exists in the DB, append `-2`, `-3`, etc. |

**Examples:**
- `vanwijk-2026-backup-cbf` — "Generalizations of Backup CBFs" by D. van Wijk (2026)
- `ames-2026-safe-locomotion` — "Safe Locomotion via CBFs" by Ames (2026)
- `unknown-2025-conformal-prediction` — paper with no listed authors (2025)
- `unknown-2025-conformal-prediction-2` — a second paper from 2025 with the same slug base

**When generating IDs for new papers:**
1. Build the base slug from `{lastname}-{year}-{keyword1}-{keyword2}`
2. Load the full set of existing IDs from `papers_database.csv`
3. If the base slug is already taken, append `-2`, `-3`, etc. until unique
4. Set the `id` column value **before** appending to the CSV — never leave it empty

---

# Interests Database Schema

Maintain a CSV file (`interests_database.csv`) with these columns:

| Column | Description |
|--------|-------------|
| `interest_name` | Name of the research interest (e.g., "Data-driven verification") |
| `category` | "application" or "method" |
| `priority_level` | "core", "high", "key", "medium", "low-moderate" |
| `relevance_mapping` | "definitely", "probably", or "mildly" — how papers matching this interest should be ranked |
| `status` | "confirmed" (active), "suggested" (pending user review), or "rejected" (dismissed) |
| `related_to` | Other interests or topics this connects to |
| `discovered_from` | How this interest was found: "manual" (user-specified) or paper titles/descriptions |
| `date_added` | Date this interest was first added |
| `date_updated` | Date this interest was last updated (e.g., status change) |
| `notes` | Explanation of why this interest might be relevant |

## Interest Discovery Rules

During each run (Mode 1 or Mode 2), after processing papers:

1. **Identify candidates** — Look for recurring themes, methods, or application areas in the papers that don't match any existing interest in the database (regardless of status).
2. **Threshold** — Only suggest an interest if it appeared in 2+ papers, OR if a single paper is very closely related to existing confirmed interests.
3. **Skip rejected** — Never re-suggest an interest that has status "rejected".
4. **Add to CSV** — Append new suggested interests with `status="suggested"`, best-guess priority and relevance, and a `discovered_from` note explaining which papers triggered it.
5. **User review** — The website's Interests tab shows suggested interests with Approve/Dismiss buttons. When the user clicks a button, the CSV is updated (downloaded for replacement). Future runs respect the updated status.

## How Interests Drive Filtering (Dynamic Relevance Model)

Relevance is computed **dynamically at display time** by the website, not baked in at ingestion. This means changing an interest's `relevance_mapping` in the Interests tab immediately affects how all papers matching that interest are ranked — no re-processing needed.

### At ingestion time (Claude):

1. Read all rows from `interests_database.csv`
2. For each paper, determine which confirmed interests it matches → store in `matched_interests` (pipe-separated exact `interest_name` values)
3. Assign a `residual_score` (integer, typically -1, 0, or +1) to fine-tune relevance
4. Set the static `relevance_tier` column as a snapshot fallback (used only when `matched_interests` is empty)

### At display time (website JS):

1. For each paper, look up its `matched_interests` against the current `allInterests` array
2. Find the highest `relevance_mapping` score among matching confirmed interests (definitely=3, probably=2, mildly=1)
3. Add the paper's `residual_score`
4. Clamp to [1,3] and map back: 3→definitely ("Must Read"), 2→probably ("Interesting"), 1→mildly ("Tangential")
5. **Must Read has to be earned:** a 3 stays Must Read only if the paper matches **two or more** confirmed "definitely" interests, or has `residual_score` +1. Otherwise it shows as Interesting. (This keeps Must Read to roughly the top fifth of the database.)
6. **Top Papers order:** Must Read papers are ranked by `(best interest score + 0.5 per extra Must Read interest + residual) × 0.5^(days since date_found / 90)`, so strong papers stay near the top for about a season. The list can also be viewed by week.
5. If `matched_interests` is empty, fall back to the static `relevance_tier` column

### Residual score guidelines:

The residual score is a **rare exception**, not a routine adjustment. The vast majority of papers (80%+) should have `residual_score = 0`. The interest-based system should do most of the work — if you find yourself assigning many non-zero residuals, the interests database probably needs updating instead.

- **+1**: Reserved for papers that are **exceptionally** relevant beyond what their matched interests capture. The bar is high: the paper must directly address data-driven verification of black-box robotic systems (Sumanth's exact research focus), or represent a genuinely novel intersection of 3+ core interests that none of the individual interest scores would reflect. Simply matching multiple interests is NOT enough for +1 — that's what the max-score logic already handles. Ask: "Would removing this +1 meaningfully misrank this paper?" If no, leave it at 0.
- **0**: The default for the vast majority of papers. Interest-based relevance is appropriate as-is. When in doubt, use 0.
- **-1**: Paper is less relevant than matched interests suggest. Use when: the paper is purely theoretical with no data-driven, learning, or robotics component; the paper only tangentially touches the matched interest (e.g., uses CBFs as a minor baseline comparison); or the paper is from a different domain (power systems, NLP) despite keyword overlap.

---

# Groups Database Schema

Maintain a CSV file (`groups_database.csv`) with these columns:

| Column | Description |
|--------|-------------|
| `group_name` | Display name of the group (e.g., "Safety & Verification"). Must match exactly the values used in `theme_groups`. |
| `status` | "confirmed" (shown on website), "suggested" (pending user review), or "rejected" (dismissed) |
| `description` | Short description of what papers belong in this group |
| `display_order` | Integer controlling the order groups appear on the website (lower = earlier) |
| `date_added` | Date this group was added |
| `notes` | Additional notes, e.g. what papers triggered a suggested group |

## Group Discovery Rules

During each run (Mode 1 or Mode 2), after assigning `theme_groups` to papers:

1. **Read `groups_database.csv`** at the start of Step 5 to get the current canonical confirmed list.
2. **If a paper fits no existing confirmed group** AND represents a genuinely new research area, create a new row in `groups_database.csv` with `status="suggested"`. Assign the suggested `group_name` to the paper's `theme_groups`.
3. **Skip rejected** — Never re-suggest a group that has `status="rejected"`.
4. **Threshold** — Only suggest a new group if it is clearly distinct from all confirmed groups and meaningfully describes 1+ papers in the current run.
5. **User review** — The website's Interests tab shows suggested groups with Approve/Dismiss buttons. Approved groups get `status="confirmed"` and appear in future runs. Dismissed groups get `status="rejected"`.
6. **Suggest topics like interests** — besides papers that fit no group, suggest a topic when a recurring theme (3+ papers in the database) isn't captured well enough by the confirmed topics to browse by. At most 2 per run. The `description` must say what belongs in it: it decides the papers when the topic is approved.
7. **Approved topics get their existing papers** — approving a topic in the dashboard tags the existing papers at once through the bridge (`bridge/add_topic.py`: Claude decides read-only, the script applies and publishes from `~/.scholar-bridge/repo`); if the laptop isn't reachable, the next run does it (Step 0.5). Done topics carry "Existing papers tagged <date> (<n>)" in `notes`.

## How Groups Drive Display

Groups are purely a display layer — they are not used for filtering or ranking.

1. Read confirmed groups from `groups_database.csv`, sorted by `display_order`
2. For each paper, split `theme_groups` on `|` and fan into matching confirmed group cards
3. Papers whose groups are all rejected/suggested simply don't appear in any group card (acceptable)
4. The `Other` group catches papers that don't fit any specific group

---

# Encrypted Notes (`annotations/`)

Notes, highlights and comments the user makes in the dashboard live in `annotations/`, **encrypted in the browser** with a password only the user knows (AES-256-GCM; key from PBKDF2-SHA256, 600,000 rounds). The repo only ever holds ciphertext.

- `annotations/_vault.json`: salt, round count and an encrypted check value (no secrets)
- `annotations/_index.json`: encrypted list of which papers have notes, and the user's highlight-colour names
- `annotations/<paper id>.json`: encrypted notes, highlights, comments and Apple Pencil ink (`ink`: strokes as page fractions) for that paper

**Digest runs and other tasks must never create, edit, move or delete anything in `annotations/`.** The files can't be read without the password, and changing them can destroy the user's notes. If a paper is ever merged into another id, leave its notes file alone and tell the user.

---

# Chat with Claude (bridge/)

The reader's **Chat** tab talks to Claude through **Claude Code on Sumanth's laptop**: `bridge/scholar_bridge.py` is a small local server (127.0.0.1:7823, started at login by `bridge/install_bridge.sh` as a LaunchAgent) that runs `claude -p` with one session per paper and streams replies to the page. It answers only the dashboard's origins, needs a pairing token (granted through a macOS dialog), and runs Claude with no shell, no MCP servers or plugins, file access limited to `~/.scholar-bridge/work`, plus web search/fetch.

- State lives in `~/.scholar-bridge/` (token, chats/, work/papers, work/library.tsv), never in this repo.
- The page sends the paper's text on a chat's first message, and the user's decrypted highlights/comments/notes and research interests with each message. Claude Code keeps the transcripts in `~/.claude/projects/` (unencrypted, on the laptop only).
- Claude cites passages as `[[p.N "exact words"]]` (clickable pills in chat and in notes), adds notes/highlights only when asked (```` ```note ```` / ```` ```highlight p.N color "words" ```` blocks), and asks for another paper with ```` ```paper <id>``` ````, which makes the page send that paper's text and notes.
- From an iPad: `bridge/tailscale_setup.sh` publishes the bridge on the user's private Tailscale network (HTTPS, `tailscale serve`); the page stores that address in localStorage `claude_bridge_url` and pairs as usual (Allow on the Mac). The Mac must be awake.
- Digest runs never touch `bridge/` or `~/.scholar-bridge/`.

# Link previews (`p/`)

Chat apps preview a link from its static HTML and never see the part after `#`, so each paper has a tiny page `p/<id>/index.html` (title, authors, venue as Open Graph tags) that forwards to `#paper/<id>`. While a paper or its reader is open, the app's address bar shows `<root>/p/<id>/#...`, so a copied link previews the paper.
- The pages are generated from `papers_database.csv` by `make_share_pages.py`, which `sync_to_github.sh` runs before every commit (it also removes pages of papers no longer in the database). Never edit them by hand.
- Uploaded (private) papers never get a page and keep the plain address.

# Uploaded papers (usually papers to review)

Library → **To review** lets the user upload a PDF and use the same reader, notes and chat. These papers are confidential and **never go into `papers_database.csv`**:
- ids are random (`up-` + 12 hex characters), so nothing about the paper shows in file names;
- the record (title, PDF fingerprint) lives in the browser (localStorage `scholar_uploads_v1`) and inside the encrypted `annotations/_index.json`; the PDF stays in the browser's IndexedDB;
- chat tells Claude the paper is a confidential submission (no web searches for it). Removing one deletes its record, local PDF and notes, and the bridge's chats, PDF copy and Claude Code transcripts (`POST /paper/forget`, accepted only for `up-` ids).

Digest runs never add, dedupe against or otherwise touch uploaded papers.
