# A new topic: which of the existing papers belong in it

A new topic (a "group" in `groups_database.csv`) was just added to the user's Scholar Dashboard: they created it, or
approved one a digest run suggested. You decide which of their existing papers belong in it. You do **not** write any file: `bridge/add_topic.py` applies your answer.

You get the topic's **name** and its **description** of what belongs in it. The papers are in
`topic_papers.tsv` in the current folder (tab-separated: id, title, headline, current topics, first 400 characters
of the abstract). Read all of it (in chunks if needed); use Grep to find more candidates by keyword, but decide on
each paper from what it is about, not from a keyword.

## Deciding
- Follow the description literally, including what they said it applies to (for example "papers proposing
  policies or verifying them").
- Tag a paper when the topic is central to it: its method, its object of study, or what it evaluates or verifies.
  A passing mention, a related-work sentence, or one baseline is not enough.
- Being in another topic already is no reason to leave it out; papers can have several topics.

## Answer
Reply with **only** one fenced JSON block:

```json
{"ids": ["paper-id", "..."]}
```

`ids` may be empty.
