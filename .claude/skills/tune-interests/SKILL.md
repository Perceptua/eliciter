---
name: tune-interests
description: Tune the arxiv interest profile — the categories the weekly sweep pulls from, and the interest and exclude terms it orders papers by — from what the user has been reading and writing, especially the papers they marked read (for interests and categories) and rejected (for excludes). Proposes changes with a reason each and asks for approval before saving anything. Use when the user wants to tune, update, review or look at their interests, exclude list or arxiv categories, asks why the sweep keeps surfacing the wrong papers or missing the right ones, or asks what the profile is. For choosing this week's papers use the reading-queue skill.
---

# Tuning the interest profile

`state/interests.json` holds three lists:

    categories  the arxiv categories a sweep pulls from — what can be seen at all
    interests   what the user cares about — a paper scores on these
    exclude     the counterweight — each one an abstract contains costs it points, so the
                field's sense of a shared word ("agents" as LLM tool-callers) sinks

Categories decide what is swept; the terms decide the order of `sweep.sh titles`. Since
the session-picks change, scores **order**; they do not filter. So a good profile puts the
papers the user would read near the top of a 1000-plus-title list, and a bad one buries them
below where a session stops reading carefully — or, for a missing category, never fetches
them. Tune for ordering and coverage, not for gatekeeping.

The profile replaced the old `ELICITER_INTERESTS`, `ELICITER_EXCLUDE` and
`ELICITER_ARXIV_CATEGORIES` settings, which no longer exist; `.env` has nothing to say about
these lists, so never read it for them.

## The loop

1. **`bash scripts/interests.sh gather`** — writes `state/interests-material.json`. If it
   reports a source unavailable, say so before going on; a tuning without the notes is a
   tuning on less evidence, and the user should know. Note the date of the last sweep
   (`state/candidates.json`): the swept counts are only as current as that.
2. **Read the evidence, in this order:**
   - `profile` — the current lists, when they were last tuned, and the recent history with
     its reasons. Do not re-propose something the history shows the user turned down or
     reversed, unless the new evidence is clearly different.
   - `papers_read` — **the strongest evidence for interests and categories.** These are
     papers the user chose to read. For each, ask what they are *about* in the user's sense,
     and whether a current interest names that. `profile_hits` lists the profile terms
     that match it, exactly as the ranker matches. A read paper with empty
     `profile_hits.interests` is one the profile did not see coming — the clearest sign of a
     missing term.
   - `term_stats` — **the ranker's-eye view, and the place to start the arithmetic.** For
     every profile term: how many read, rejected and freshly swept papers it matches. A
     term in hundreds of swept papers is a firehose. One with read > 0 and few rejected is
     earning its place; one with read 0 and many rejected is costing the ordering. Quote
     these counts in each `why`.
   - `category_stats` — per primary category: read, rejected and swept counts, and whether
     the profile sweeps it now. **A category with read papers that is not in the profile**
     means the user went and found those papers by search — the strongest case for adding
     it. A swept category with a large swept count and nothing read or queued from it is
     costing the sweep its `ELICITER_ARXIV_MAX_RESULTS` budget, and is the case for
     dropping one. Counts are by primary category, and a sweep also fetches papers
     cross-listed into a swept category, so `swept` can be non-zero for a category that is
     not in the profile — that is cross-listing, not a sign it was swept.
   - `papers_rejected` — **the evidence for excludes.** `profile_hits.interests` says which
     interest pulled each one in; `matched` is the ranker's view from when it was swept.
     Look for a *pattern*: the same field, the same vocabulary, across several rejections.
     One odd rejection is not a pattern.
   - Then the writing and other reading — `notes`, `posts`, `misc`, `tweets`, `books`,
     `sessions`. This is where an interest shows up **before** any paper on it has: a run of
     notes on, say, renormalisation is a reason to add it even with no read paper yet.
     Skim; it is large. You are looking for preoccupations, not reading for detail.
   - `since_last_tuning` marks the papers decided since the last change. Weight those, but
     the older ones still count — they are what the current profile was meant to catch.
3. **Propose.** Write `state/interests.next.json`. Every block is optional:

   ```json
   {"note": "one line on what this tuning is about",
    "categories": {"add":  [{"term": "quant-ph", "why": "…"}],
                   "drop": []},
    "interests":  {"add":  [{"term": "renormalisation", "why": "…"}],
                   "drop": [{"term": "alignment", "why": "…"}]},
    "exclude":    {"add":  [{"term": "red-teaming", "why": "…"}],
                   "drop": []}}
   ```

   Then **`bash scripts/interests.sh check`**. It validates every entry against the profile
   (an add already present, a drop not there, a term in both interests and exclude, a
   malformed category name, a missing `why`, a list left empty) and prints the proposal one
   line per change. Fix and re-check until it passes.
4. **Ask.** Show the user the `check` output, and for each change the evidence behind it —
   name the papers (title and id) or the notes. Ask them to approve, edit or strike
   changes. **Nothing is saved without an explicit yes.** If they strike or reword some,
   rewrite the proposal, `check` again, and show the result before saving.
5. **`bash scripts/interests.sh save`** — only after approval. It applies the proposal,
   appends it to the profile's history with its reasons, and removes the draft. The next
   sweep uses it; the UI shows the new lists on its next refresh.

A tuning that finds nothing worth changing is a fine result. Say so, with what you checked,
and write no proposal.

## What makes a good term

The ranker is bag-of-words over title and abstract, with one exception: **a multi-word term
matches as a phrase.** `collective intelligence` scores only where those words run together;
stopwords between them are skipped, so `philosophy of time` matches "the philosophy of time".
Matching is on exact lowercase tokens with no stemming — `agent` and `agents`, `behaviour`
and `behavior` are different. So:

- **A phrase is precise; a single word is a blunt instrument.** A one-word interest lifts
  every abstract containing it; a one-word exclusion sinks every one. Check a single word's
  swept count before proposing it — `entanglement` (4 of a 1462-paper week) is fine,
  `memory` (137) is not. The `.env` comment this profile came from deliberately kept
  "learning", "language", "system", "policy" and "fine-tuning" out of the exclude list —
  the last because the fine-tuning argument is a philosophy-of-physics topic the user
  wants. Apply the same care.
- **A phrase has to be what the papers actually write.** It matches only that run of words,
  so take it from the read papers' abstracts, not from how the user would describe the
  topic. Before proposing a phrase, check it matches at least one read paper or a fair
  number of swept ones — count with `rank.contains(text, term)` over
  `state/candidates.json` and the queue. A phrase nobody writes matches nothing.
- **An exclude must be the field's word, not the user's.** Before proposing one, check it
  matches none of the read papers. If it does, it would sink papers like the ones the user
  chose — say so, and don't propose it.
- **Dropping is as useful as adding.** An interest that caught nothing read and several
  rejected is costing the ordering. But a term with no hits yet may be a standing interest
  the week has not served — check the notes before calling it dead.
- Keep each list a list of things, not sentences. Terms are compared case- and
  space-insensitively; commas are not allowed in a term.

## What makes a good category

- **Add on read papers, not on topic.** A category earns a place when papers the user read
  came from it (they found them by search) or when the notes have moved into its field.
  Quote the read papers in the `why`.
- **Every category costs budget.** A sweep pulls at most `ELICITER_ARXIV_MAX_RESULTS`
  papers across all categories, newest first; a large category (cs.LG, cs.AI, quant-ph
  run to hundreds a week) crowds the others toward the newest day or two. When proposing a
  large one, say so, and mention that the user may want to raise that cap in `.env`.
- **Drop on silence.** A category that has been swept for weeks with nothing read, queued
  or noted from it is costing budget for nothing.
- Names are arxiv's own: an archive (`quant-ph`, `math`) or archive.subject (`cs.AI`,
  `physics.hist-ph`). The check rejects anything else.

## Looking, not tuning

- `bash scripts/interests.sh` — the lists, and when they were last tuned.
- `bash scripts/interests.sh history` — every change with its reasons.

The user may also just tell you a term or category to add or drop. That is still a
proposal: write it, `check` it, show it, and save on their yes — the history should say
why, in their words.
