---
name: elicit-tweets
description: Run a tweet-writing conversation with the user — find live topics in their recent reading and writing, pitch them one at a time, help them compose the tweet in their own words, and save each one they finalize as a draft on eliciter's Tweets tab. Use when the user wants to write tweets, says they have something to post, asks what they could tweet about, or asks to rebuild / look at their voice profile. Also covers importing an X archive into the tweets source and marking a draft posted. For essays, notes, journal entries and verse use elicit-writing.
---

# Writing tweets, together

**You do not write the user's tweets.** The first version of this skill had a session
batch out 2–3 drafts per topic in their voice. The user called the result "spectacularly
bad", and they were right: a voice profile and a pile of sources produce pastiche, which
means long sentences, attribution-heavy setups and a joke bolted onto the end. What works is
a conversation. You find what is live, put it in front of them, and help them say it. The
words start with them.

## The session

```
gather → read → shortlist ≤3 topics ─┬→ pitch one ─→ pass  → log it, next topic
                                      │             └→ engage → compose together
                                      │                          → they call it done → save draft
                                      │                          → another on this topic? / next
                                      └→ wrap: after 3 topics, or when they say so → lessons
```

1. **Gather and read.** Run `bash scripts/gather.sh`, then read `state/material.json` and
   `state/voice.md` in full. Read three things first:
   - `tweet_lessons`: what earlier sessions learned. Follow it.
   - `previous_tweets.topics`: every topic pitched before, with its outcome.
   - `previous_tweets.dormant`: topics they passed on, each with what they have read or
     written since. See *Topics they passed on*.
   - `previous_tweets.drafts`: what they finalized, and what they actually posted.

   If a source is under `unavailable`, say so.
2. **Shortlist up to three topics, privately.** See *Finding topics* below. Do not show
   the list; they see one topic at a time.
3. **Pitch one.** See *A pitch*. Then stop and wait.
4. **They pass or engage.**
   - **Pass:** ask, in a few words, whether there is a reason (optional; do not press).
     Log it:
     `bash scripts/tweets.sh topic --title "…" --source <src>:<ref> --outcome passed --note "…"`.
     Then pitch the next topic.
   - **Engage:** compose (below). Each tweet they call finished is saved immediately:
     `bash scripts/tweets.sh draft --title "<topic>" --source <src>:<ref> … --text "<exact text>"`.
     Confirm the length it printed, then ask whether they want another on this topic or the
     next one. When the topic is done, log it with `--outcome drafted`.
5. **Stop after three topics, or the moment they say to wrap.** Log any topic you pitched
   and did not finish as `--outcome skipped`. Then write the lessons (below).

## Finding topics

You are looking for **what they are actively thinking about**. In order of strength:

1. **A reading their own writing has answered.** A paper marked read (`papers.read`,
   `read_on`) or a book finished (`books`, `finished`) followed by a note, misc entry, post or tweet that takes it up: quoting it,
   arguing with it, or using its terms. Check by date and by substance, not shared
   vocabulary. A note written two days after the paper and in its terms is the strongest
   signal in the material. Say what you found and the dates.
2. **Their own recent writing**: new notes in their own words (many indexia notes are
   quotations; those show what they are reading, not what they think), misc entries, a
   recent post.
3. **Recent reading with no response yet.** These are the weakest. Pitch one only if the
   first two kinds are exhausted, and say plainly that nothing of theirs has answered it.

### Topics they passed on: dormant until new material

A topic the user passed on is **dormant**. It may be pitched again only if they have
**read or written something since that bears on it**. `previous_tweets.dormant` lists each
passed topic with `newer`: everything dated after the pass, meaning notes, misc, posts,
tweets, papers marked read and books finished or being read. That list is candidates, not verdicts.

- **`newer` is empty:** nothing has happened since. The topic stays down. Do not pitch it,
  and do not mention it.
- **`newer` has items:** read them and judge whether any genuinely bears on the topic in
  substance, not by shared words. A new note on Aristotle does not revive a passed topic
  about fungi.
  - **If one does,** the topic is eligible again, and its pitch must open with what is new:
    "You passed on this on Nov 17; since then you read X and wrote Y." That way the user
    is deciding about the new material, not the old pitch.
  - **If none does,** it stays dormant.
- **Re-pitched and passed again:** it is dormant again from the new date (log it as
  `passed` like any other).

**`skipped` is not dormant.** A topic you ran out of time for was never turned down, so it
can be pitched again freely. Skip topics already drafted or posted, unless they asked for
more on it.

Recordings and private notes may inform a topic, but a tweet must never quote or link
private material without the user's say-so.

**Three is a ceiling, not a target.** If only one topic is genuinely live, pitch one. If
nothing is, say so.

## A pitch

Keep it short, and make it something they can say yes or no to in a second:

- **The topic, in a line.**
- **The evidence:** what you found, with dates and titles. For example: "You read the
  measurement-problem paper on Sept 21 and took four notes from it the same day; one is
  in your words: '…'."
- **The thing worth looking at:** a quoted line, a phrase, an exact particular (a page
  number, a word like *Spitzenkörper*). Their tweets are made of exact particulars; hand
  them some.
- **Then ask.** Ask one open question about what struck them. Never offer a draft or an
  angle disguised as a question.

## Composing

- **They write first.** Ask what they think or what struck them. Their answer, even a
  rough one, is the material. The tweet is usually already in it.
- **You edit; you do not author.** Offer cuts, word swaps, a reordering, a sharper last
  clause, always as a change to *their* sentence: "If you drop 'actually', it lands on
  'dreaming'." If they ask you to try a full phrasing, you may, once, and label it as
  yours. Then go back to theirs.
- **Keep it in their voice** (`state/voice.md`, and `## Yours` above everything):
  - standard capitalization;
  - `&` for "and";
  - unspaced em dashes;
  - one sentence;
  - a plain setup and a turn at the end;
  - no hashtags or emoji.

  When an edit would pull away from the profile, say so rather than doing it quietly.
- **Count as you go.** Report the length (URLs count as 23) whenever the text changes
  materially. Their tweets run 130–180 characters; past about 200, suggest a cut.
- **Facts are checked, claims are theirs.** If the tweet credits a paper with a claim,
  check it against the abstract in the material. Never add a position they have not taken.
- **"Done" means done.** Save the exact text they approved, character for character.
  Don't fix their punctuation on the way into the file.

## Wrapping up: lessons for next time

At the end of every session, append a dated section to `state/tweet-lessons.md`
(gitignored; create it if missing). Write 2–6 bullets on what would make the next session
better:

- which kinds of topic they engaged with or passed on, and why;
- edits of yours they accepted or rejected, and what that suggests;
- how much help they wanted (more questions? fewer suggestions?);
- anything about their voice that the profile gets wrong.

Show them the bullets and invite corrections. The next session reads this file first
(it arrives as `tweet_lessons` in the material).

Some lessons belong elsewhere:
- If a lesson is really about **their voice**, offer to add it to `## Yours` in
  `state/voice.md`. That section is theirs, so ask first.
- If it is about **how this skill should work for anyone**, suggest editing this file.

## The voice profile

`state/voice.md` is built from tweets (register) plus notes, perceptua and misc
(vocabulary, preoccupations). Rebuild it when `voice.stale` is true or the user asks. Write
the rebuild to `state/voice.next.md` with these sections:

- Register
- Vocabulary
- Preoccupations
- What lands
- Examples (verbatim tweets with refs)
- Yours

**Copy `## Yours` byte for byte.** Then run `bash scripts/tweets.sh voice-check` and
`voice-save`. The save stamps the build with the tweet count, which is what makes it go
stale when tweets are added. Describe the voice; do not flatter it. Draw vocabulary only from
their own sentences, never from the quotations in their notes.

A stale profile does not block a session. Mention it, and offer to rebuild at the end
rather than spending the start of their session on it.

## Drafts, and after

Drafts appear on the Tweets tab, newest first, and each open one sits in `tweets/drafts/`.
When one goes out, **Posted this →** with the post's link or id (or
`bash scripts/tweets.sh posted <n> --id <id|link>`, with `--text "…"` if it changed) saves
the text into `tweets/<date>-<id>.md`, where it becomes source material and voice evidence.
The id is required: it names the file the same way the archive import does, so a later
import never duplicates it. A draft marked posted before ids were required can be given one
with the same command. **✗ Not this
one** marks it rejected. `bash scripts/tweets.sh show` lists drafts and recent topics.

**Revising a draft** that has not gone out: `bash scripts/tweets.sh revise <n> --text "…"`
(and/or `--title "…"`). Never edit `state/tweets.json` by hand. The draft keeps its number,
sources and status, and the old text goes into `revisions`. A posted draft is refused; if
what went out differed from the draft, that is `posted <n> --text "…"`. When a session
finds drafts with `revisions` in `previous_tweets.drafts`, read them: the edits the user
made after calling it done are the plainest evidence of what the session missed, and
belong in the lessons.

## Importing the archive

Archive downloads go in `tweets/archives/`; with no argument, the import reads the newest
zip there.

```bash
bash scripts/import-tweets.sh --dry-run
bash scripts/import-tweets.sh
bash scripts/import-tweets.sh ~/Downloads/twitter-YYYY-MM-DD.zip   # or name one
```

This writes one `.md` per original tweet into `tweets/` (gitignored):
- A tweet with a photo or video keeps its text; the media and its link are dropped.
- Replies (including thread continuations), retweets and picture-only tweets are skipped.
- `t.co` links are expanded.
- The archive wins: a tweet already in `tweets/` is refreshed from it when they differ
  (likes, retweets, exact text). Re-running the same archive changes nothing.

Every posted tweet is named `YYYY-MM-DD-<id>.md` (UTC date), however it arrived, so the
import never duplicates one already marked posted; it refreshes it.
