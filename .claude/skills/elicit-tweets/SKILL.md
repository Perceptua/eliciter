---
name: elicit-tweets
description: Draft tweets in the user's voice for eliciter's Tweets tab, and build or refresh the voice profile they are written in. Use when the user asks for tweets, something to post, what they should tweet, ultra-short posts, or to rebuild / refresh / look at their voice profile. Also covers importing an X archive into the tweets source and marking a drafted tweet posted. For essays, notes, journal entries and verse — the prompts that never contain drafts — use the elicit-writing skill.
---

# Drafting tweets

**This is the one place in eliciter where you write in the user's voice.** Everywhere else
the machine proposes the site and the human writes — a prompt with a thesis in it is wrong
(see `elicit-writing`). The Tweets tab is a deliberate, fenced exception the user asked
for: each card names a site, like a prompt, and then carries **two or three drafted
tweets** for them to pick from, edit, post, or turn down.

The fence matters as much as the exception:

- Drafts live **only** in `state/tweets.json`. Never put drafted prose into
  `state/prompts.json`, a brief, or a writing session — those keep the old rule.
- A draft may only say what the user has already said. A position in a draft has to be one
  they hold in their own notes, posts, misc or tweets; a paper's claim is attributed to the
  paper ("this paper finds…"), never adopted on their behalf. You are writing *in* their
  voice, not putting new opinions in their mouth.

```
 scripts/gather.sh → state/material.json ─┐
                     state/voice.md ──────┼→ YOU → state/tweets.json → scripts/tweets.sh render
   (rebuilt by you when stale) ───────────┘                          → prompts/tweets-latest.md
```

## The loop

1. **Ask before replacing a run that is still standing.** If `state/tweets.json` has open
   cards and the user did not clearly ask for fresh ones, show them
   (`bash scripts/tweets.sh show`) and check. A run where everything is posted or
   rejected is spent and can be replaced without ceremony.
2. **Gather.** `bash scripts/gather.sh`, every time — the same rule as prompts.
3. **Read `state/material.json`** — all of it, `tweets` and `voice` included. Say so if a
   source is under `unavailable`.
4. **The voice.** If `voice.stale` is true, or the user asked, rebuild it (below). If not,
   read `state/voice.md` and use it as it is.
5. **Write `state/tweets.json`** (schema below).
6. **`bash scripts/tweets.sh check`** until it passes, then **`bash scripts/tweets.sh
   render`**. Never hand-write the markdown.
7. Show the user the cards and stop. They post; you don't.

If `tweets` is empty there is no voice evidence. Say so, point them at
`bash scripts/import-tweets.sh <archive.zip>`, and do not invent a voice from the long-form
writing alone — the long-form register is not how anyone tweets.

## The voice profile

`state/voice.md`, gitignored. **Tweets set the register; everything else sets the
substance.** Their tweets tell you length, casing, punctuation, whether they use hashtags
or emoji or links, how a tweet opens and how it lands. Their notes, perceptua posts and
misc writing tell you their vocabulary and what they keep returning to.

Write the rebuild to **`state/voice.next.md`**, never straight over `state/voice.md`:

```markdown
# Voice

## Register
How a tweet of theirs is built: typical length, casing, punctuation (em dashes? ellipses?),
hashtags/emoji/links or their absence, one-liners vs two-beat, questions vs statements.

## Vocabulary
Words and constructions they reach for, from all sources. Words they never use — the
ones an LLM would reach for and they don't — are as useful as the ones they do.

## Preoccupations
What they keep coming back to, across tweets, notes, posts and misc.

## What lands
Patterns among their most-liked tweets (`likes` in the material). Observed, not prescribed;
say how many tweets it rests on.

## Examples
8–12 of their tweets, verbatim, that best show all of the above, each with its ref.

## Yours
(copied exactly from the current state/voice.md — see below)
```

Then `bash scripts/tweets.sh voice-check`, and when it passes, `bash scripts/tweets.sh
voice-save`. `voice-save` stamps the build time and tweet count — that stamp is what makes
the next gather call it fresh — and moves it into place.

**`## Yours` belongs to the user.** It is where they write overrides by hand ("never say
'delve'", "no threads"). Copy it from the current `state/voice.md` byte for byte; on a
first build, leave it empty. `voice-check` refuses a rebuild that changed it. What it says
**overrides everything else in the profile** when you draft.

Describe; do not flatter. "Lowercase, no hashtags, usually one sentence, often ends on a
question" is a profile. "Witty and insightful" is not.

## What makes a card

Aim for **3–6** cards. Fewer is fine; none is a real answer (`"quiet": "why"` in the JSON).

- **Site first.** Same sources as prompts: a paper they marked read, a note, a recording,
  a post, a misc fragment, one of their own older tweets worth returning to. Prefer what is
  recent and live. Cross-source sites are as good here as anywhere.
- **Every draft should be postable as it stands**, ≤280 characters as X counts them (a URL
  costs 23). `check` enforces the limit.
- **The drafts on a card differ in kind**, not in wording: e.g. a plain statement, a
  question, a quote-and-react. Three paraphrases of one sentence is one draft.
- **Sound like the Examples, not like a model.** Match their casing and punctuation. No
  hashtags, emoji, "🧵", "Hot take:", "Here's the thing", "It's not X, it's Y" or
  rhetorical triplets unless the profile shows *them* doing it.
- **Link only when the site is public** (an arxiv paper, a published perceptua post). Notes,
  recordings and misc are private; a draft may draw on them but never cite or link them.
- **`previous_tweets` is history.** `rejected` is an answer — do not reissue it reworded.
  `posted` is done, and its `posted_text` is the best voice evidence you have: what they
  actually sent, after their edits.

## The schema

`state/tweets.json`:

```json
{
  "cards": [
    {
      "title": "short label for the card",
      "site": "What it is about, one line — the paper, note, recording.",
      "because": "Past tense, factual: what you saw that made it surface now.",
      "sources": [{"source": "arxiv", "ref": "2511.01234", "title": "…", "why": "optional"}],
      "drafts": ["first draft", "second draft", "optional third"]
    }
  ]
}
```

`sources` must be real refs from `state/material.json` — `tweets` is a valid source (a tweet
filename), alongside `indexia`, `perceptua`, `misc`, `audua`, `arxiv`. Leave out `n` and
lengths; they are derived.

## After they post

The Tweets tab's **Posted this →** (or `bash scripts/tweets.sh posted <n> --draft <k>`,
with `--text "…"` for an edited version) marks the card and saves the text into `tweets/`
as one `.md`. That is how new tweets enter the source from now on, and why the voice goes
stale after each one — the profile should keep learning from what they actually post.
`reject` and `reopen` work as for prompts.

## Importing the archive

```bash
bash scripts/import-tweets.sh ~/Downloads/twitter-YYYY-MM-DD.zip --dry-run
bash scripts/import-tweets.sh ~/Downloads/twitter-YYYY-MM-DD.zip
```

One `.md` per original tweet in `tweets/` (gitignored). Replies (including thread
continuations), retweets and tweets with media are skipped and counted; `t.co` links are
expanded and HTML entities unescaped. Re-running adds only what is new.
