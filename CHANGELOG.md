# Changelog

`copier-ui` and `copier-tui` share one version and are published to PyPI in lockstep, so every entry below covers both packages.

## v1.0.22 (2026-08-29) - Changelog

- Added this file, reconstructed from the version-bump commits back to v0.6.1; releases from here carry an entry of their own

## v1.0.21 (2026-08-29) - Header leads with the project, tree gap under a parent closed

- The header's title cell reads `<project> ⸱ <context> ⸱ <position>`, with the project name and the field counter in the bright accent and the context between them in plain ink - the two facts nothing else on the screen carries are the two that stand out
- `copier-tui v<version>` moved out of the title into the right-hand cell; it says the same thing on every screen of every run, so it no longer competes with the run's own state
- The three title parts crop in the order they can be spared: the position never, the project from the left behind `...`, the context from the right - so the field counter survives at 60 columns despite now sitting last
- The blank line above a focused conditional row carries the tree rail when the row above is the question it hangs from, not only when it is a sibling; the first child of an answer no longer shows a gap between that answer and its own connector
- A bool row names no key under itself - two options are read off the row - while a multiselect still names `space` and a choice still says the key cycles its options
- `docs/acc-crit-copier-tui.md` and `docs/defects-copier-tui.md` migrated to the tracked `pm-tools` schema: severities renamed to the CRITICAL / MAJOR / MEDIUM / MINOR vocabulary, all 133 criteria rated for importance, evidence and test hints derived from the closure records already in the files, and a repro line written for every defect that lacked one
- README drops the MIT badge, tints the two PyPI badges apart, and carries the review and execution screenshots beside the survey one; all three SVGs regenerated

## v1.0.20 (2026-08-27) - Pale orange cursor blink at half the rate

- The cursor mark's second blink state is `ORANGE_PALE` (`#ffdcb0`), a step off white rather than a saturated orange
- The mark switches ink every eight phases of the focus bar's 32-phase cycle, about 0.48 s a state

## v1.0.19 (2026-08-27) - Faster, brighter cursor blink

- The mark switches ink every four phases of the bar's cycle, four times the previous rate
- The second state is a brighter orange than the muted accent it started from

## v1.0.18 (2026-08-27) - Cursor blinks white and orange, destination leads its row

- The cursor square no longer breathes through a cyan ramp, which washed out against the blue focus bar; it blinks between two plain states on the bar's own clock
- The survey's status row opens with `destination: <path>` on the left and the hint to its right; the crop rules are unchanged

## v1.0.17 (2026-08-27) - Finish banner, project in the header, destination named

- The execution screen closes on a content-sized banner over the file log: on success it counts files added, changed, deleted and left with a conflict - a `.rej` beside the file or an inline `<<<<<<<` marker - and lists the conflicted paths; on failure it carries copier's own reason, and any key closes it
- New `changes.py` snapshots the destination before and after the render by digest, pruning `.git`, so the count is a before-and-after account rather than a guess
- The header names the destination project on every screen, cropped from the left behind `...` when too wide; the review header's full path was saying the same thing at greater length and is gone
- The survey's destination line reads `destination: <path>`, takes the row that the hint leaves, and re-fits from its own resize
- The cursor square on an option row breathes with the focus bar rather than on a timer of its own

## v1.0.16 (2026-08-27) - Final screen closes on any key, destination is a real path

- `enter` and `escape` hung the app at `press any key to close` in every release: both were bound to an action, and `Screen.dismiss()` called from inside an action dispatch waits on that dispatch. The bindings are gone and every key takes one route
- Abandoning a render walks `/proc` descendants and stays armed for children started late; the terminal is handed back cooked
- `update` defaults its destination to the working directory, which the survey showed as `.` - the one name a reader cannot check anything against. New `paths.py` resolves it, writes it home-relative with `~`, crops long paths from the left behind `.../`, measures in cells rather than characters, and survives a machine with no home directory
- The cursor mark is U+25FC with inverted ink, distinct from a picked option; option labels wrap cell-aware, so emoji and CJK never paint past the row

## v1.0.14 (2026-08-27) - Survey status row takes one row, not half the screen

- The rule styling `#survey-status` at one row matched nothing, because the Horizontal holding the key legend and the destination carried no id. It fell back to `height: 1fr`, so the screen split its rows between two `1fr` children - at 164x55 the form was laid out at 26 rows of the 51 available, overflowed, and scrolled while the rows below stayed blank
- The destination is cropped to its one row through CSS `text-wrap` and `text-overflow`; Textual's visual pipeline drops a Rich `Text`'s own `no_wrap` and `overflow`
- Mouse reporting is off, so selecting and copying text works the way it does anywhere else in the terminal

## v1.0.13 (2026-08-27) - Option rows decide their layout once they have a width

- `InlineOptions` chose one line or a stack against a guessed 42 columns while it had no width of its own, so a long question opened four lines tall, repainted on one line when the real width arrived, and left the vacated lines on screen until something else redrew that patch
- `_fits` now answers one line while the width is unknown, so a row grows into its stack instead of shrinking out of it; the guessed budget is gone
- A test records every paint and allows none to stack at a width that holds the options

## v1.0.11 (2026-08-27) - The keyboard survives a template task

- Copier runs a template's tasks as ordinary subprocesses holding this process's own descriptors, so under `--trust` a task inherited the terminal Textual holds in raw mode: it read the keystrokes meant for the form, and a task that prompts left the tty in its own mode
- Everything the render starts now gets `/dev/null` for stdin through a patched `subprocess.Popen`; this process's own descriptor 0 is never swapped, since Textual's input thread is reading it
- The line discipline is snapshotted and restored around the render, so a task that cooks the terminal cannot leave the form waiting for a newline before it sees a key
- A pty-driven test runs the whole app against a fixture whose tasks do both, and requires a bare keystroke to close it

## v1.0.10 (2026-08-26) - The tree crosses the cursor's gap

- The blank line the focused row keeps either side of itself was padding, which takes the row's ground but is empty by definition, so landing the cursor inside a run of children cut the connector column in half. The spacing is now two spacer widgets of the row's own, carrying the run where a sibling sits across the gap
- The option cursor mark takes each shade from the row's own beat rather than a timer of its own, so mark and focus bar cannot drift out of phase

## v1.0.9 (2026-08-26) - Wrapped child captions clear the connector

- A caption longer than the label gutter folded its second line back to column zero, under the connector, putting prose where the tree is. Any template whose questions carry real help text rather than bare variable names hit it
- The caption is wrapped by the row rather than left to Rich, which has no hanging indent; lines after the first carry the run down on a child with siblings below it

## v1.0.8 (2026-08-26) - Conditional questions hang off the answer that decides them

- A question another answer gates leans its ground green on either band, and carries the same lean into its typing ground, since a control spans the row
- A tree connector before the caption hangs the question off its answer; consecutive children of one answer share the run and only the last closes it
- No connector when the governing answer came in with `--data`, since the row it would hang from is never asked for

## v1.0.7 (2026-08-24) - Neutral answers, an orange edit, a breath instead of steps

- Settled answers moved off pale yellow onto a neutral grey brighter than the captions at 7.43:1; a tint on thirty settled answers read as a warning about all of them
- The answer being edited turns orange rather than amber, as saturated as the lightest ground on the form allows at 4.56:1
- The focus bar rides 32 cosine-eased phases at 0.06 s instead of four shades a third of a second apart, so no frame moves a channel more than 10 of 255

## v1.0.6 (2026-08-24) - The header names the template

- The header reads `<template> questionnaire - N of M` rather than `survey`: which template is being filled in is the one fact none of its own questions carries
- The name is a property of the template rather than of the rendering, so `copier_ui` reads it back off copier's worker instead of the command line - on an update there is no argument, since copier takes the source from the answers file - and drops a `.git` suffix, which names the transport rather than the template

## v1.0.5 (2026-08-24) - Chosen is said in the shape

- An option carries a filled circle when it is the answer and an empty one when it is not, so being chosen is said in the glyph as well as the ground; both measure one cell, so the label column does not shift
- The chosen chip moved to a deeper blue that can carry white text at 6.39:1; white on the brand cyan measured 2.70:1, and the dark ink it needed instead read as struck out rather than chosen

## v1.0.4 (2026-08-24) - Every option is a chip

- An unchosen option was bare text, and bare text beside chips reads as one more option - a question's caption ended up looking like one of its own answers
- Every option carries a ground in one of three states: chosen, under the cursor, and passed over. Only the answer changes hue, so being chosen is never inferred from which neutral is brighter, and none of the three is dimmed out of legibility

## v1.0.3 (2026-08-24) - The first 1.x: the render gives the keyboard back

- `press any key to close` was dead after a real render, because a template's tasks inherit this process's descriptors and read the keystrokes meant for the form. The render now runs with stdin on `/dev/null` and restores it afterwards
- Descriptors 1 and 2 are left alone deliberately - Textual paints through 1, and blanking it would take the progress bar and the verdict with it

## v0.6.11 (2026-08-24) - Options on the row, questions grouped without a copier concept

- `Schema.groups` partitions questions in declaration order behind the `_ui_groups` opt-in key, which copier carries through and ignores; a template naming no groups gets one untitled group, so a frontend has a single code path
- `Question.condition_ids` names the questions a `when` reads, so a conditional field can nest under the answer that governs it without the frontend parsing the expression
- Every option is printed on the question's own row: nothing opens over the form, and the alternatives stay legible beside the one in force

## v0.6.9 (2026-08-22) - Questions are captioned, not named

- A UX review found the survey unreadable to anyone meeting the template for the first time. The label is now copier's own rendered prompt message, so a caption is what copier itself would ask; `var_name (type)` appears only when the template declares no help
- Help outranks the open-the-list hint on the reserved line, which had been suppressing it on every choice field
- The caption gutter is a share of the terminal, ellipsis-marked, with the full caption on the hint line

## v0.6.8 (2026-08-22) - First PyPI release of both packages

- `escape` is handed back to an expanded `Select`, so an open dropdown closes instead of arming a quit
- An armed cancel lapses after three seconds instead of holding for the session
- The README screens are captured from a real render, so the execution screen reports files that were actually written

## v0.6.7 (2026-08-22) - Escape belongs to an open list first

- Escape on the survey is a priority binding, so it pre-empted a dropdown's own escape: backing out of an open choice list armed a quit instead of closing the list. The screen hands escape to an expanded `Select` and keeps it everywhere else - a multiselect is an `OptionList` but not a menu, so it still arms the cancel
- Editing an answer disarms an armed cancel, and the header counts the focused field of the total so the eye keeps an anchor while scrolling

## v0.6.5 (2026-08-22) - One row per question

- The survey took four rows per question - label, help, control, error - so a 35-question template ran to 172 rows and several screens. It is now one row: a right-aligned label gutter, a flat compact control, and a single status glyph
- Help and validation messages share one reserved hint line that follows the focus, so they cost no rows at all; the reference template's 24 questions fit one 40-row screen
- Review is stacked over the survey instead of replacing it, so going back keeps the scroll offset and the focused field, and the form still recalculates every dependent answer after the round trip

## v0.6.4 (2026-08-22) - Functional tests run against the throwaway venv

- The reference template's post-generation task shells out to a bare `python3`, which on the CI runner resolved to the system interpreter and failed after writing the whole tree - a failure that could not reproduce locally
- The throwaway venv's `bin` goes first on `PATH`, so `python3` resolves to the interpreter holding the template's dependencies, which is what an activated venv gives a real user

## v0.6.3 (2026-08-22) - Unit and functional suites, six defects fixed

- 125 unit tests and 8 functional tests; the functional suite runs against the built wheels in a throwaway venv, the same way CI does
- Two of the defects made the package unrunnable and had never been hit because nothing had executed it once: `HeaderBar` assigned `self._context`, shadowing Textual's `MessagePump._context` so every message pump died, and `ExecutionScreen._render` shadowed `Widget._render`, so the compositor invoked the copier run on the UI thread during layout

## v0.6.1 (2026-08-22) - Two-package uv workspace

- `copier_ui` and `copier_tui` moved under `packages/`, each with its own pyproject, README and PyPI metadata, under a virtual uv workspace root carrying ruff, pytest and the dev group
- `scripts/bump_version.py` bumps the shared patch number and moves the exact `copier-ui` pin in `copier-tui`; `make install` runs it every time
- `make publish` uploads both distributions with twine, `copier-ui` first; `make test-functional` builds both wheels and runs the functional suite against them in a throwaway venv
