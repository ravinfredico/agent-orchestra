# ChaCha PA: design

Direction: **Thread with a cast.** A quiet, monochrome chat. Agents are the only color on screen.
Each one is a character whose face shows its status, so cards need very few words.

Source of truth for visuals: the design canvas (private to you)
https://claude.ai/artifact/1VhNwtUMKpMpNrVvbyhNUS
- Page "Style & components": the Thread sheet (tokens, components) and the Character component.
- Page "Screens": 9 desktop screens, 4 phone screens, and the shared Sidebar, Rail and TaskCard.

Artboard links below use `<canvas>#artboard-<name>`.

## 1. Information architecture
```
Desktop                                         Phone
┌──────────┬───────────────────────┬────────┐   ┌──────────────┐
│ Sidebar  │ Thread                │ Rail   │   │ Header       │
│ New run  │ header: title, status │ Usage  │   │ Team strip   │
│ Today    │ messages, task cards  │ Team   │   │ Thread       │
│ Earlier  │ composer / run bar    │ Files  │   │ Run bar      │
│ Plan mode│                       │        │   └──────────────┘
└──────────┴───────────────────────┴────────┘   Files, options: bottom sheets
```
- **Sidebar** (260 px): app name, New run, runs today, earlier runs, All runs, plan-mode indicator,
  theme switch.
- **Thread** (max 720 px, centered): the run as a conversation.
- **Rail** (320 px): usage, team, files. Hidden on the new-run and history screens.
- Below 1100 px the rail folds into a "Team & usage" button in the thread header. Below 760 px the
  sidebar becomes a menu button, and the phone layout takes over.

## 2. Screens
| # | Screen | Artboard | What it shows |
|---|---|---|---|
| 1 | New run | `S1-New` | Sleeping orchestrator and checker, "What should the team do?", big composer, options panel, starter suggestions. |
| 2 | Run in progress | `S2-Live` | Your message, orchestrator plan, agents joining, task cards, activity line, run bar with Stop, rail. |
| 3 | Task fails, team replans | `S3-Retry` | Failed card with checker lines per try, orchestrator's replan, new agent joins, old card crossed out, new card working. |
| 4 | Finished | `S4-Done` | Summary, file chips, "All done" card with happy faces, follow-up box. |
| 5 | Out of budget | `S5-Budget` | What works and what doesn't, full meter, "Continue with $2 more", See files, Run again. |
| 6 | Crashed | `S6-Crash` | "Your Claude login expired", 3 steps, Try again, technical details folded. |
| 7 | History | `S7-History` | Search, outcome filters, runs grouped by day with team faces, status, usage. |
| 8 | File viewer | `S8-Files` | File list with author characters, rendered report.md, Copy, Raw, Download all. |
| 9 | Live, light theme | `S9-Live-Light` | Screen 2 in light mode. |
| P1 | Phone new run | `P1-New` | Greeting, suggestions, composer at the bottom. |
| P2 | Phone live run | `P2-Live` | Team strip of faces, thread, run bar with meter and Stop. |
| P3 | Phone files | `P3-Files` | Bottom sheet with file chips and the rendered file. |
| P4 | Phone history | `P4-History` | Runs list with search and New run. |
| T1 | Team room | `M8-Teams` | Sidebar Teams section, room (your bubbles right; orchestrator, hand-offs "orchestrator → agent" and checker results left; system lines centred), message box, team panel (goal, members with tier chips, triggers in words, memory, Edit, Pause). Below 1280 px the panel is a drawer opened from the header. |
| T2 | Team editor | `M8-Teams` | Name, time zone, goal, members (name, role, model, tool chips), schedule slots (cron + task), webhook toggle with task and URL, memory, Save, Cancel, Delete (asks twice). |
| R1 | Replay page | `M6-Replay` | The run screen without the sidebar, a header with "Replay · a recorded run, no live agents" and a GitHub link, and a player instead of the run bar: play/pause, position slider, event count, speed 1× 2× 4×. The end card is "Replay finished" with the result and Play again. |
| — | Message during a run | `M8-Teams` | A message box above the run bar while live: "Message the orchestrator. It reads this at its next step." Your message joins the thread at once as a user bubble. |

Built in the app but not yet drawn on the canvas: the **approval card**, the **interrupted** outcome,
the **stop confirmation**, the **playbook line** and **Playbook select** (Auto or one playbook, with its
one-line description under it), and the **connectors & plugins picker** in the Options panel (chips;
greyed out with "Not set up" when credentials are missing; outward ones are labelled "asks first").

## 3. Components and every state

### 3.1 Character
A rounded square body in the agent's color, white eyes, dark features. Size 18 to 88 px.
Props: `color`, `mood`, `accessory`, `size`, `label` (screen reader text).

| Mood | Face | Used when |
|---|---|---|
| neutral | open eyes, flat mouth | just hired, or in a message |
| working | eyes looking down-right, small "o" mouth | attempt running |
| waiting | eyes as flat lines | checker is verifying |
| happy | smiling arcs, smile | task passed, run finished |
| sad | worried brows, frown | attempt failed, task failed, out of budget |
| sleepy | closed curved eyes | idle, queued, replaced, crashed, interrupted |

Fixed cast:
- **Orchestrator:** violet `#9D8CFF` with a bow tie.
- **Checker:** grey `#C9C9CF` with a monocle.

Agent colors, in creation order: `#FF8A6B`, `#4FC7B8`, `#F5C451`, `#B48CE0`, `#7FA6FF`, `#F29FC5`.
After 6 they repeat, with an antenna accessory added to tell them apart.

### 3.2 Task card
Character (36 px) + title (15/600) + status line (13, text-2, with a 7 px dot) + attempt dots.

| State | Mood | Status line | Dot | Attempt dots |
|---|---|---|---|---|
| queued | sleepy | Queued | border | ○ ○ ○ |
| working | working | Working · try N | text | done, current ring, empty |
| checking | waiting | Checking · try N | check | current ring |
| retrying | sad, then working | Try N · <short reason, max 5 words> | check | fail dots, current ring |
| done | happy | Passed | pass | fails, filled |
| not started (dependency failed, M7) | sleepy | Not started · <title> failed | fail | none |

On the right, before the dots, a mono tier chip names the model of the current try (`haiku`, `sonnet ↑` after a step-up). Open, the card shows the tier and its reason, the cheap checks, and per try the tier and either the checker's reason or each check with ✓ or ✕ ("checks, no model asked"). Canvas: `M7-Cheaper`.
| failed | sad | Failed · N tries | fail | all fail |
| replaced | sleepy | Replaced by <new title> | border | none; card at 55% opacity, title struck |

Tap or Enter opens the card in place: "Done when: …", then one checker line per try
(checker character + "Try N" + reason). Escape or a second tap closes it.

### 3.3 Messages
- **Your message:** right-aligned bubble, surface-2, radius 20.
- **Orchestrator:** character (32 px) + plain text, no bubble.
- **Joined line:** small character(s) + "<name> joined", with "· can search files" style hints when
  a notable tool is added.
- **Playbook line:** small book icon + "Using the **Research report** playbook", 13.5 px, text-2,
  indented like joined lines. Shown once, right after your message.
- **Activity line:** three dots + "<agent> is <doing>". Only the newest one per agent shows.
  It disappears when the attempt ends.

### 3.4 Composer and run bar
| State | Looks like |
|---|---|
| Empty | Placeholder "Give the team a task, and say how to tell it's done". Start disabled. |
| Typing | Start enabled (primary circle). Enter adds a line; Cmd/Ctrl+Enter starts. |
| Options open | Options button highlighted, panel below with all run options: shell, playbook, repo, connectors, then Preset (Default, Cheap; Custom once a field is edited), Orchestrator, Workers (Orchestrator picks, or Always <tier>), Highest model, Checker, usage cap, max agents, tries per task, steps per try, max tasks, tasks at once. Canvas: `M7-Cheaper`. |
| Running | Becomes the run bar: team faces, "Running", elapsed and usage, Stop. |
| Replanning | Run bar says "Replanning". |
| Waiting for approval | Run bar says "Needs your approval". |
| Ended | Becomes a follow-up box: "Start a follow-up run…" plus Run again. |

### 3.5 Approval card (new)
Shown in the thread when an outward tool is called.
- Agent character (waiting mood) + "<agent> wants to <action>".
- The exact payload in a mono box (for example the email's to, subject and first lines).
- Buttons: **Approve** (primary), **Deny**.
- States:
  - **Pending:** card has a check-color border, and the run bar says "Needs your approval".
  - **Approved:** card collapses to "Approved · sent".
  - **Denied:** card collapses to "Denied".
  - **Expired:** the run was stopped before you answered; the card shows "Not answered".

### 3.6 Outcome cards
| Outcome | Character(s) | Title | Body | Buttons |
|---|---|---|---|---|
| Finished | all happy | All done | Main file, task count, time, usage | Open <file>, Run again |
| Out of budget | orchestrator sad | Out of budget | Used of cap, what passed | Continue with $X more, See files, Run again |
| Crashed | orchestrator sleepy | Plain cause ("Your Claude login expired") | Numbered fix steps | Try again, Copy error details |
| Stopped | orchestrator sleepy | Stopped by you | Tasks passed before stopping | See files, Run again |
| Interrupted | orchestrator sleepy | Interrupted | "The server restarted. Files are kept." | Continue, Run again |

### 3.7 Usage meter
- 4 px track, surface-2. The fill uses text color, or check color at 85% and above.
- Label: "$1.99 est. of $5". Near the cap: "$2.81 of $3 · almost out" in the check color.
- Rail extras: elapsed, agents used / max, tasks used / max.
- It updates in steps when attempts end. No fake smoothing.

### 3.8 Sidebar run item
Dot + title (one line, ellipsis):
- text = running
- pass = finished
- check = out of budget or waiting for approval
- fail = crashed
- border = stopped or interrupted

The active item gets a surface-2 background and `aria-current="page"`.

## 4. Motion
Easing: ease-out `cubic-bezier(.23,1,.32,1)` for UI, drawer `cubic-bezier(.32,.72,0,1)` for sheets.

| What | Motion | Duration |
|---|---|---|
| New message or card | rises 8 px, fades in | 220 ms |
| Several at once | stagger | 40 ms apart |
| Agent hired | character scales 0.9 to 1 | 240 ms |
| Working | character bobs 2 px | 1.4 s loop |
| Blink | eyes close and open | 120 ms every 4 to 6 s, random per character |
| Passed | one small hop | 300 ms |
| Sent back | head shake, 2 × 2 px | 240 ms |
| Status change | chip text and dot cross-fade with 2 px blur | 180 ms |
| Sheet open / close | slides from bottom | 320 ms / 240 ms |
| Button press | scale 0.97 | 120 ms |

Rules:
- Only `transform` and `opacity` are animated.
- Live updates use CSS transitions so a quick second change retargets smoothly.
- Nothing animates on keyboard shortcuts.
- **Reduced motion:** expressions still swap and fades stay, but nothing moves (no bob, hop, shake or rise).

## 5. Tokens

### Color
| Token | Dark (default) | Light | Use |
|---|---|---|---|
| bg | `#0A0A0A` | `#FFFFFF` | page |
| surface | `#151515` | `#F6F6F6` | cards, composer |
| surface-2 | `#222222` | `#ECECEC` | your bubble, tracks, active item |
| text | `#F5F5F5` | `#0A0A0A` | primary text |
| text-2 | `#A3A3A3` | `#5C5C5C` | secondary text |
| border | `#2A2A2A` | `#E6E6E6` | hairlines |
| primary | `#F5F5F5` | `#0A0A0A` | send, main buttons |
| on-primary | `#0A0A0A` | `#FFFFFF` | text on primary |
| pass | `#4ADE80` | `#15803D` | dot, word |
| fail | `#F87171` | `#B91C1C` | dot, word |
| check | `#FBBF24` | `#A16207` | dot, word, near limit |
| focus | `#93C5FD` | `#1D4ED8` | focus ring |

Status colors appear only as small dots or words, never as large tinted areas.

### Type
Geist for text, Geist Mono for ids, files, money and time.

| Role | Size / weight |
|---|---|
| Greeting, history title | 26 to 34 / 600, tracking -0.03em |
| Outcome title | 18 / 600 |
| Card title, header | 15 / 600 |
| Messages, body | 15 / 400, line height 1.55 |
| Status line, meta | 13 / 400 |
| Rail labels | 12 / 500, uppercase |
| Mono | 13 / 400 |

### Space and shape
- Spacing scale: 4, 8, 12, 16, 20, 24, 32, 48.
- Radius:
  - composer 28
  - bubble 20
  - card 16
  - inputs 12
  - chips and buttons pill
  - phone sheet 28 at the top
- Touch targets: at least 44 px. Desktop secondary buttons can be 36 to 40 px.

## 6. Responsive and phone
| Width | Layout |
|---|---|
| 1280+ | Sidebar, thread, rail |
| 1100 to 1279 | Sidebar, thread. The rail opens as a side panel from "Team & usage". |
| 760 to 1099 | Thread only. Menu button opens the sidebar as a drawer. |
| under 760 (phone) | Header (menu, title, files count), team strip of faces, thread, run bar at the bottom with meter and Stop. Options and files open as bottom sheets. History is its own screen. |

Phone rules:
- The run bar stays fixed at the bottom above the safe area.
- The thread scrolls under the header, which stays visible.
- The team strip scrolls sideways when there are more than 5 agents.

## 7. Microcopy
| Place | Copy |
|---|---|
| Greeting | What should the team do? |
| Composer placeholder | Give the team a task, and say how to tell it's done |
| Options summary | $5 cap · shell off (Cheap preset: Cheap · $1 cap · shell off) |
| Shell option | Allow shell commands. Needed for code and tests. Commands run on this machine. |
| Repo option | Work in a repository (optional). Needs a clean git tree. The team works on a new branch, so your main branch is never touched. |
| Running | Running · 00:24 · $0.74 est. |
| Stop confirm | Stop this run? The current attempt is cancelled. Finished tasks and files are kept. [Keep running] [Stop run] |
| Joined | researcher joined |
| Activity | analyst is reading research/dana.md |
| Approval | editor wants to send an email to … [Approve] [Deny] |
| Finished | All done. Every task passed the checker · 52s · $1.99 est. |
| Out of budget | Out of budget. Used $3.06 of the $3.00 cap. [Continue with $2 more] |
| Crashed (login) | Your Claude login expired. Run `claude` in a terminal, then `/login`, and press Try again. |
| Crashed (limit) | You've hit your plan's usage limit. It resets at <time>. |
| Interrupted | Interrupted. The server restarted. Files are kept. |
| Empty files | Files appear here as agents write them. |
| Empty history | No runs yet. Start one and it will show up here. |
| Plan mode | Pro plan · plan login · no API key / API key · billed per use |
| Repo refused | That folder has uncommitted changes. Commit or stash them first, so agent edits don't mix with yours. |

Voice: plain, short, says what happened and what to do next. Never blame the user.

## 8. Accessibility
- **Keyboard:**
  - Everything is reachable with Tab in visual order.
  - A "Skip to content" link is the first Tab stop. It jumps past the sidebar.
  - Closed drawers (sidebar, rail) are hidden from Tab and screen readers. Opening one moves focus
    into it. Escape closes it and focus returns to the button that opened it.
  - Dialogs keep Tab inside until closed. Row menus focus their first item and Escape returns to the
    menu button.
  - Focus never ends up under the sticky header or run bar (scroll padding).
  - Cards are buttons. Enter or Space opens them, Escape closes.
  - Cmd/Ctrl+Enter starts a run.
  - Focus moves to the dialog on Stop confirm and returns to Stop after.
- **Focus:** a 2 px focus-color ring with a 3 px offset on every interactive element. Never removed.
  Text fields that sit inside a styled box (composer, follow-up, search) show the ring on the box.
- **Faded states:** never fade text below 4.5:1. A replaced card fades only its face and dots; its
  title is struck through in text-2.
- **Contrast:** all text pairs pass 4.5:1 in both themes. Faces use dark features on light bodies,
  so they read on black and white.
- **Screen readers:**
  - Each character has a label: "analyst, waiting on checker". Inside a task card the face is hidden
    and the card's name is "analyst: Compare fees, Passed on try 2", so the status is read once.
  - Decorative faces in stacks are `aria-hidden`.
  - Meters use `role="meter"` with values.
- **Live announcements:** one `role="status"` region with `aria-atomic="true"`, polite. It announces
  only these, one short sentence each:
  - agent joined
  - task passed
  - attempt sent back (with reason)
  - task failed
  - task replaced
  - approval needed (assertive)
  - run finished, out of budget, crashed or stopped

  Activity lines and usage changes are never announced. Events that were already in the log when the
  page opened are never announced (the page reads `last_seq` first). Several events at once are read
  together in one sentence each.
- **Color is never the only signal:** every status has a word and a face.
- **Motion:** honors `prefers-reduced-motion` (section 4).

## 9. Event to UI map
Every live event (see ARCHITECTURE.md) has a home in the UI:

| Event | UI |
|---|---|
| run_started | Your message, run bar "Running" |
| playbook_chosen | Playbook line: book icon + "Using the <title> playbook" |
| orchestrator_said | Orchestrator message |
| user_message | Your bubble in the thread (and in the team room); announced "You said: …" (M8) |
| nudge | Nothing visible (raw log only) |
| agent_created | Joined line, rail team row, run bar face |
| task_assigned | New task card (queued; "Queued · waits for <title>" when it has unfinished dependencies). Tier chip and reason on the card (M7, canvas `M7-Cheaper`) |
| attempt_started | Card working / retrying, character working. Tier chip updates on a step-up |
| attempt_failed / task_passed with `checked_by: checks` | Card detail shows each check with pass or fail, "no model asked" (M7, canvas `M7-Cheaper`) |
| worker_activity | Activity line |
| file_written | Rail files list, file count badge |
| checker_started | Card checking, character waiting |
| attempt_failed | Card retrying with reason, character sad |
| task_passed | Card done, character happy (hop) |
| task_failed | Card failed (with `attempts: 0`: "Not started", M7) |
| task_replaced | Old card crossed out |
| approval_requested | Approval card, run bar "Needs your approval", push |
| approval_resolved | Approval card collapses |
| usage | Meters. Rail "By model" bar and list, "By agent" rows with cost, a thin bar, models used (haiku → sonnet after a step-up) and tasks or checks (M7, canvas `M7-Cheaper`) |
| budget_exhausted | Meter turns check color, "almost out" then outcome |
| finished | Finished or Out of budget outcome card |
| run_failed | Crashed outcome card |
| run_stopped | Stopped outcome card |
| run_interrupted | Interrupted outcome card |
