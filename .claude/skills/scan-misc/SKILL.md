---
name: scan-misc
description: Transcribe a photo/scan of a handwritten page into a markdown file in eliciter's misc/ source folder. Use when the user has dropped an image into misc/ (or points to a picture of handwritten notes) and wants it turned into material eliciter can read — "scan this", "OCR my notecard", "turn this photo into a misc source". Whole-page verbatim transcription, with a human ratification step before anything is written.
---

# Scan a handwritten page into misc/

Turn an image dropped in eliciter's `misc/` folder into a `.md` file `eliciterlib/misc.py`
will pick up on the next `scripts/gather.sh`. Your job is **faithful transcription and
preparation — never authoring, never summarizing.** This skill does not touch any other
part of eliciter, and it never runs `scripts/gather.sh` or writes to `state/` itself.

This is modeled on indexia's `transcribe-notes` skill (`../indexia/.claude/skills/
transcribe-notes/SKILL.md`), which does the equivalent job for the graph. The transcription
discipline is identical; what differs is the destination and the shape of the output — a
misc file is read whole by a session judging prompts (like a perceptua post or an audua
summary), not decomposed into one-idea Zettelkasten notes. So **do not split a page into
several files** the way `transcribe-notes` splits a card into several notes. One image
becomes one markdown file, preserving the page's own structure (headings, paragraph breaks,
numbered points) rather than atomizing it.

## The one hard rule: verbatim

**Transcribe exactly what is written. Do not re-word, summarize, paraphrase, condense,
expand, translate, or "clean up."** The words in the file must be the human's, character for
character.

- Preserve wording, spelling, capitalization, and punctuation as written — do **not**
  silently autocorrect. If something is clearly a slip, point it out for the human to fix
  during ratification; you do not fix it yourself.
- Illegible text → write `[illegible]` (or `[?best-guess]` for a genuine guess). Never invent
  words to fill a gap.
- Keep the page's own line and paragraph structure, and any headings or numbering the author
  wrote. Drop only trivial layout artifacts (page-edge shadows, a margin ruled line).
- **No invented titles.** Only give the file a heading if one is literally written on the
  page; otherwise the plain transcription is enough — `misc.py` titles the file from its
  filename, not from front matter.

## Formatting conventions

Three fixed transcription choices, settled once so they don't need re-deciding per page:

- **Underlined words become italics.** A word the author underlined is written `_word_` in
  the markdown, not wrapped in `<u>` tags or left as a bare underline. Underlining on a
  handwritten page and italics in rendered markdown do the same job — marking emphasis — so
  this is a format change, not a content change.
- **Crossed-out words are skipped, unless told otherwise.** Don't transcribe a struck-through
  word at all — not with `~~strikethrough~~`, not in brackets. The author already discarded
  it; carrying it into the file is noise the material doesn't need. If the human explicitly
  asks to preserve a crossing-out on some page (e.g. the revision itself is the point), do
  that instead for that page only — this default is for the ordinary case.
- **Em dashes take no surrounding spaces.** Write `this—that`, not `this — that` or
  `this -- that`, regardless of how the author spaced it on the page — this is normalized
  the same way a struck-through word is dropped, because it's a typographic convention, not
  content.

## Steps

1. **Find the image.** Look directly in `misc/` (PNG/JPG/PDF, `misc/*.png` etc. — the same
   folder text and markdown files get dropped into; images just aren't read by `gather.sh`
   until this skill converts them). If several are present, handle one at a time and confirm
   which if it's ambiguous which page is which.

2. **Transcribe** the full page verbatim, per the rule above.

3. **Ratify (required — write nothing yet).** Show the human the full proposed transcription
   as it will be written, plus the filename you intend to give it. They may approve as-is,
   correct specific words or lines, or ask you to re-read part of the image. **Write nothing
   until they explicitly approve.**

4. **Write the ratified transcription.** Pick a filename from the image's own name (slugified,
   lowercase, hyphens for spaces) with a `.md` extension, e.g. `staging-notes-page-3.jpg` →
   `misc/staging-notes-page-3.md`. If a file by that name already exists, ask before
   overwriting — never overwrite a misc file silently. Write only the ratified body; no YAML
   front matter, no added heading, no metadata block. `misc.py` reads the whole file as the
   material and derives the title from the filename and the date from the file's own mtime,
   so nothing else needs to go in it.

5. **Move the source image aside**, so it isn't mistaken for an unprocessed scan on a later
   pass:
   ```bash
   mkdir -p misc/processed
   mv "misc/<image>" misc/processed/
   ```
   `misc/processed/` is invisible to `eliciterlib/misc.py` — it only reads files directly
   inside `misc/`, not subdirectories — so moving the image there is enough; nothing needs to
   be told about it.

6. **Tell the user** the file is written and where, and that the next `scripts/gather.sh` (or
   the next time a session is asked for prompts, since gathering happens automatically then)
   will pick it up as a `misc` source.

## Notes and gotchas

- **Ratification is a hard gate**, exactly as in `transcribe-notes`. A misreading of
  handwriting silently written to a source a Claude session later reads as fact is worse
  here than in indexia, not better — a bad transcription becomes bad material for a prompt,
  with nobody to catch it before it's read.
- **One file per image, whole-page.** If the human explicitly asks for a page to be split
  (e.g. it's actually two unrelated fragments on one sheet), that's their call to make during
  ratification — propose it, don't decide it.
- This skill never imports `eliciterlib.readonly` and never needs to — it's the one place
  writing *into* `misc/` is correct, the same way `scripts/write.sh` opening a session in
  indexia or perceptua is the correct place for *those* sources to be written. See the
  read-only-sources skill for why that's not a hole in eliciter's read-only gate.
- No database, no `ARCADEDB_ROOT_PASSWORD`, no indexia dependency at all — this only touches
  files inside eliciter's own `misc/` folder.
