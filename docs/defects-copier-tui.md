# Defects - copier-tui

Observed wrong behaviour in `copier-ui` and `copier-tui`, one item per symptom, with the trail of what has been tried against it. Acceptance criteria live in [acc-crit-copier-tui.md](acc-crit-copier-tui.md).

## Survey screen `SRVY`

- [x] `DEF-SRVY-1` **survey body cut vertically short while the status bar spans the full width** - HIGH; the question list occupies only the upper part of the terminal and the body is clipped, while the bottom status bar still spans the full screen width; seen on `copier-tui update --trust` at 164x55 against 1.0.13; cause under investigation - suspect the `_Form` VerticalScroll reporting a virtual height larger than its content; `packages/copier-tui/src/copier_tui/screens/survey.py`
  - related: ACC-TUI-55, ACC-TUI-54 - the layout criteria this violates
  - log: 2026-08-27 added
  - log: 2026-08-27 reported: "the screen is garbled, some part of the screen has items, but the screen is cut vertically short, while still having fullscreen bottom statusbar" (v1.0.13)
  - log: 2026-08-27 reported: "it is worse than it was before" - a regression against an earlier release, first suspect is the 1.0.13 `InlineOptions._fits` change to first-paint heights in `inline.py`
  - log: 2026-08-27 closed: fixed: the status row now carries the id its own CSS rule was written for, so it takes one row instead of a Horizontal's default 1fr; the form gets every row the chrome is not using - 51 of 55 at the reported 164x55, against 26 before; tests/unit/test_tui_survey.py
- [x] `DEF-SRVY-2` **scrollbar drawn and the form scrolls with content filling only the upper half** - MEDIUM; a scrollbar is painted and the survey scrolls although the settings occupy only the upper half of the terminal; content that fits must neither scroll nor show a bar; cause under investigation - likely the same oversized virtual height as DEF-SRVY-1; `packages/copier-tui/src/copier_tui/screens/survey.py`
  - related: DEF-SRVY-1 - same suspected oversized virtual height, likely one fix
  - related: ACC-TUI-55 - content that fits one screen must not scroll
  - log: 2026-08-27 added
  - log: 2026-08-27 reported: "we display scrollbar and make settings take only upper half of the screen, and still scroll" (v1.0.13)
  - log: 2026-08-27 closed: fixed: with the form at full height its content fits and no scrollbar is drawn - max_scroll_y 0 where it was 9; a form that genuinely overflows still scrolls, tested at 60x20; tests/unit/test_tui_survey.py
- [x] `DEF-SRVY-3` **destination path is not visible anywhere on screen** - MEDIUM; the path the template will be rendered into is not shown in the running TUI, although `test_the_survey_says_where_the_template_will_be_rendered` passes against `#survey-where`; cause under investigation - the test reads widget state rather than painted output, and the widget may be clipped by DEF-SRVY-1; `packages/copier-tui/src/copier_tui/screens/survey.py`
  - related: DEF-SRVY-1 - the clipped body may be why the widget never reaches the screen
  - related: ACC-TUI-76 - the criterion this violates
  - log: 2026-08-27 added
  - log: 2026-08-27 reported: "path where the template will be rendered isn't shown anywhere" (v1.0.13)
  - log: 2026-08-27 noted: `test_the_survey_says_where_the_template_will_be_rendered` was added in 1.0.13 and passes, so the criterion is verified against state the user cannot see - the test must read the painted screen
  - log: 2026-08-27 closed: fixed: the destination is one row, cropped with an ellipsis, through text-wrap and text-overflow in CSS - Textual's visual pipeline drops a Rich Text's own no_wrap and overflow, which is why it wrapped onto three rows; the test now reads the row's height; tests/unit/test_tui_survey.py

## Key handling `KEYS`

- [x] `DEF-KEYS-4` **double-escape only quits when the two presses are far enough apart** - MEDIUM; escape pressed twice in quick succession does not quit and the app appears to hang until a third escape or an arrow key arrives; escape, pause, escape does quit; the arming logic itself is sound - `action_cancel` arms for a 3s `CANCEL_WINDOW` - so the second press is not reaching it; cause under investigation - suspect Textual's ESC-timeout parser folding a back-to-back second escape into a pending sequence that only flushes on the next byte; `packages/copier-tui/src/copier_tui/screens/survey.py`
  - related: ACC-TUI-57 - the criterion this violates
  - log: 2026-08-27 added
  - log: 2026-08-27 reported: "esc-esc doesn't work (it hangs the tool until i pres esc again or move arrow up and down), it doesn't exit the tool" (v1.0.13)
  - log: 2026-08-27 reported: "esc esc does work, just not when pressed in short succession; we must capture double-esc regardless of how quickly"
  - log: 2026-08-27 closed: fixed: mouse motion reporting is off - App.run(mouse=False); Textual asked the terminal to report every pointer movement, and a report arriving behind the second escape became its introducer and consumed it; tests/unit/test_tui_terminal.py
