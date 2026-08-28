---
name: elicit-research
description: Help formulate ideas and find research or citations for a prompt the user has picked from eliciter, before they draft it. Use when the user has chosen a numbered writing prompt and wants to think through the angle, dig into background, or find supporting sources — not yet ready to open a writing session. For seeing what prompts are on offer use the elicit-writing skill; for the actual drafting use write.sh.
---

# Researching before writing

This sits between two things `elicit-writing` already owns: seeing the prompts, and opening
a session to draft one. It's for the gap — the user picked prompt N and wants a sounding
board and some legwork before they sit down to write it.

## Get the prompt's material

Don't re-resolve the prompt by hand. `scripts/write.py` already does that, and `--print`
shows the brief without launching a session:

```bash
bash scripts/write.sh <n> --print
```

This prints the ask, the form, the source and (for notes and papers) the material itself —
the same brief a drafting session would open with. Start from this, not from
`prompts/latest.md`, since it carries the full `detail` field the rendered list truncates.

## Formulating ideas

Talk it through like a sounding board, not a ghostwriter — same boundary `elicit-writing`
holds at the drafting stage, just one step earlier. Ask what the user already thinks about
the ask before offering an angle; the claim needs to be theirs by the time it reaches a
drafting session. Useful moves: surface the tension in a "ratified contradiction" prompt,
name candidate structures for an essay, ask what the note's title should have been if they'd
already written it.

## Finding citations

Use WebSearch / WebFetch — eliciter has no research tool of its own here.

- **If the prompt's source is a paper** (`ref` is an arxiv id), fetch
  `https://arxiv.org/abs/<id>` for the abstract and its own reference list before searching
  further afield.
- **If the user needs sources for a claim**, search normally and hand back what you find
  with enough context to judge relevance — title, venue/date, the specific claim it
  supports. Don't just list links.
- If a search turns up a paper worth reading later rather than citing now, that belongs in
  the reading queue, not stapled to this prompt — point the user at the UI's Search tab
  (`eliciter-ui` skill) rather than trying to add it yourself; there's no CLI path for it.

## Handing off

This skill produces notes and links, not prose, and eliciter still can't write to indexia or
perceptua (`read-only-sources`). When the user is ready to draft:

```bash
bash scripts/write.sh <n>
```

opens the actual session in the target project. `write.py`'s seed text is fixed — it won't
carry the ideas or citations gathered here automatically, so paste the useful ones into that
session yourself once it opens.
