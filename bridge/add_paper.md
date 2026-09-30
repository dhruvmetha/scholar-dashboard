# Adding a paper by hand: the research step

You are adding one paper the user chose to their Scholar Dashboard database. The user gave a link, DOI, arXiv id,
title or description (the **input**). Your job is to find the paper and describe it; you do **not** write any file.
A script (`bridge/add_paper.py`) checks for duplicates, makes the id, writes the row and publishes it.

The databases are in the current folder: `papers_database.csv`, `interests_database.csv`,
`groups_database.csv` (pipe-separated). Read the interests and groups files before deciding matches.

## 1. Find the paper
- Resolve the input to one specific paper. A link or DOI names it; for a title or description, search (arXiv,
  Google Scholar, the publisher, OpenReview). If two or more papers fit and you can't tell which, stop (see 4).
- Visit the paper's page and take, **from the page itself**: the exact title, the full author list (comma-separated,
  in order), the venue (conference/journal, or `arXiv`), the publication month and year (`"Mar 2026"`; year only if
  the month is unknown), and the **abstract verbatim** (never paraphrased or shortened).
- `url`: a permanent link. Prefer the arXiv abstract page, a DOI link, or an OpenReview forum. Conference sites whose
  unversioned path shows the next edition (e.g. RSS) must use the year-specific path. Check a conference link opens
  the paper (no 404).
- `pdf_url`: an open PDF the dashboard can load in the browser: `https://arxiv.org/pdf/<id>` when there is an arXiv
  version (search arXiv by exact title even for conference or journal papers), a PMLR PDF, or else empty. Leave it
  empty for OpenReview and most publishers (they block other sites).
- `arxiv_id` and `doi` when there are any (used to spot duplicates).

## 2. Describe it for this user
The user is a robotics researcher working on data-driven verification of black-box robotic systems with black-box
controllers. Use `interests_database.csv` as the definition of their interests.
- `matched_interests`: the **confirmed** interests the paper genuinely matches, exact `interest_name` values. Can be
  empty for an off-topic paper; the user still wants it in the database.
- `residual_score`: 0 almost always; +1 only when the paper is directly about data-driven verification of black-box
  robotic systems, or a real intersection of 3+ core interests; -1 when it only touches its matched interests.
- `relevance_tier`: `definitely`, `probably` or `mildly` (the best matched interest's `relevance_mapping`, adjusted by
  the residual; `mildly` when nothing matches).
- `theme_groups`: 1-2 (at most 3) exact `group_name` values of **confirmed** groups in `groups_database.csv`. Never
  `Other` or any name not in the file; leave it empty when nothing fits.
- `headline`: the takeaway in about 10-15 words (not the title).
- `summary`: 3-4 sentences: the contribution, the approach, the key result.
- `notes`: `"Added by you. {Core|High|Moderate|Low} — {one-line reason it fits, or that it is outside the usual
  interests}"`, plus `" [residual ±1: why]"` when the residual isn't 0.

## 3. Keep private papers out
The database is published in a public repository. If the paper has no public version (for example a submission under
review that the user has only as a PDF), do not describe it: stop (see 4) with the reason `private`, so the user can
upload it under Library, To review, where it stays private.

## 4. Answer
Reply with **only** one fenced JSON block, nothing before or after it:

```json
{"papers": [{"title": "", "authors": "", "venue": "", "publishing_date": "", "url": "", "pdf_url": "",
  "arxiv_id": "", "doi": "", "abstract": "", "headline": "", "summary": "", "notes": "",
  "matched_interests": [], "residual_score": 0, "relevance_tier": "", "theme_groups": []}]}
```

Several papers in the input: one object each. When you can't add it, instead:
`{"stop": "ambiguous" | "not found" | "private", "message": "one or two sentences for the user", "candidates": ["Title (Year)", ...]}`
(`candidates` only when ambiguous).
