# Final Word specification source

This directory supplies the source missing from AP-ENGINE-ALIGNMENT-001.
It is a transcription of the owner's uploaded final consolidated Word document,
not the earlier EMA10-voting specification recovered from f8a4813.

## Provenance and verification

- Source: Aperture_Structure_and_Setup_Engine_Final_Spec-1.docx
- Source byte length: 218014
- Source SHA-256: 3e8de86756299a91a592eb9a78431896e783e7d8500d6c1254d93f28f6567965
- Extraction verified against every body text node in word/document.xml:
  400 top-level paragraphs, eight tables, 624 text nodes, all in source order.
- No drawings, embedded objects, tracked insertions/deletions, text boxes, or
  Office Math objects occur in the main document.
- word-final-spec.json preserves paragraph text and table rows/cells structurally.
- word-final-spec.txt is the readable rendering: paragraphs separated by blank
  lines and table cells separated by tabs.
- Text, tabs and line breaks are extracted directly; visual formatting and
  automatic list markers are not reproduced. This is text-content verification,
  not a visual facsimile or an assertion that every rule is unambiguous.

## Authority and implementation

Read ../../APERTURE_CURRENT_AUTHORITY.md first. This is immutable source evidence.
The source's own V1 naming refers to its proposed design, not the already shipped
Git engine V1. Implement the authorized alignment using new explicit versions.

The later current authority overrides the Word's 15-session contraction age:
CONTRACTION initially 40 sessions; RANGE 60 sessions while valid.
Retain accepted Git lifecycle, timing, frozen-reference, identity, missing-data
and corporate-action safeguards. Do not blindly replace runtime Setup behavior
with every original Word rule. Resolve the current authority's provisional
choices under the authorized bounded comparison.

Map Word enums explicitly:
TRANSITION_UP -> EMERGING; TREND_UP -> UPTREND;
TRANSITION_DOWN -> DETERIORATING; TREND_DOWN -> DECLINE.
NEUTRAL is unchanged.

The Word shock test is distance from SMA50 (D50), not the Setup EP close-to-close
ShockATR measurement. Do not silently interchange them.
The source's phrase 'mirror ... wherever possible' is not a complete transition
table implementation. Document any required interpretation, including equality
handling for P20, transition precedence, counters, and transitional-state exits.
Do not import the old EMA10/15-session classifier to fill those gaps.

## Resume

Bring this source-only commit into codex/engine-alignment-v2 while preserving
the local CODEX_NEXT_TASK.md assignment update and .vscode/settings.json.
Continue the already authorized AP-ENGINE-ALIGNMENT-001; record this source hash
and the selected interpretations in the new implementation contract.
No engine, active-task file, production input, or snapshot is changed by this
source handoff.
