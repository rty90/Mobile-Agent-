# Mobile-Agent- v0.2

`Mobile-Agent-` is a practical Android GUI agent MVP for Android Studio Emulator + ADB.

The project keeps a small, testable architecture:

- low-level ADB wrapper
- atomic skills
- deterministic planner with optional OpenAI planning
- executor with screenshots, logs, expectation checks, and one recovery attempt
- compact SQLite memory
- bounded router for supported task flows

This is still an emulator-first MVP. It is not trying to be a fully general phone agent yet.

## What v0.2 supports

The repo now supports 3 stable bounded task flows:

1. `send_message`
   Send a template SMS to a remembered contact, with confirmation before send.

2. `extract_and_copy`
   Read the current screen, extract one bounded value such as an order number or check-in time, then copy/type it into Notes.

3. `create_reminder`
   Open a calendar/reminder editor, prefill the reminder title and optional time, then confirm before save.

## Current architecture

- `app/main.py`
  Unified CLI entrypoint and runtime bootstrap.
- `app/planner.py`
  Stable rule-based planning for the 3 supported task types, with optional OpenAI fallback.
- `app/executor.py`
  Executes steps, refreshes page state, records memory, and performs one recovery attempt on selected failures.
- `app/router.py`
  Small routing layer for execute, replan, confirm-first, and unsupported-task decisions.
- `app/context_builder.py`
  Builds a compact task-aware context object instead of dumping full history.
- `app/memory.py`
  SQLite memory for preferences, contacts, successes, and failures.
- `app/skills/`
  Atomic skills such as `open_app`, `tap`, `type_text`, `read_screen`, `extract_value`, and `open_calendar_event`.

## Emulator requirements

- Python 3.8+
- Android Studio Emulator running
- `adb devices` shows a connected emulator
- Google Messages available for the SMS flow
- Google Keep available for the extract-and-copy flow
- Google Calendar available for the reminder flow

Check the emulator first:

```bash
adb devices
python -m app.utils.test_actions
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run the 3 supported task flows

### 1. Send message

General CLI:

```bash
python -m app.main --task "send message to Dave Zhu \"hello from emulator\"" --task-type send_message
```

Remembered-contact runner:

```bash
python -m app.demo_runner --message-text "hello from emulator"
```

### 2. Extract and copy

Example: order number to Notes

```bash
python -m app.main --task "extract the order number and copy it into notes" --task-type extract_and_copy
```

Example: hotel check-in time to Notes

```bash
python -m app.main --task "extract the hotel check-in time and copy it into notes" --task-type extract_and_copy
```

### 3. Create reminder

```bash
python -m app.main --task "create a reminder for buy milk at 7pm" --task-type create_reminder
```

```bash
python -m app.main --task "create a reminder for call Zhang San tomorrow" --task-type create_reminder
```

## Useful CLI options

```bash
python -m app.main --help
```

Key options:

- `--task-type`
  Force one of `send_message`, `extract_and_copy`, `create_reminder`, or `unsupported`.
- `--planner-backend`
  Use `rule` or `openai`.
- `--dry-run`
  Build route + plan only, without touching the emulator.
- `--auto-confirm`
  Bypass confirmation prompts for non-interactive runs.
- `--device-id`
  Select a specific emulator/device serial.

## What gets stored

- Logs: `data/logs/agent.log`
- Screenshots: `data/screenshots/<task_name>/`
- SQLite memory: `data/memory.db`

Memory currently stores:

- `user_preferences`
- `known_contacts`
- `successful_trajectories`
- `failure_patterns`

Only verified successful trajectories are used as trusted success memory.
The agent does not store chain-of-thought or free-form reasoning history in long-term memory.

## Router behavior

`router.py` stays intentionally small.

It now decides between:

- `execute`
- `replan`
- `confirm-first`
- `unsupported-task`

The decision uses:

- supported task type detection
- high-risk keywords
- `state.needs_replan`
- repeated recent failures
- cross-app complexity

## Context behavior

`context_builder.py` keeps prompts compact and deterministic.

Per task, it includes:

- current goal
- task type
- current page / trimmed screen summary
- last 1-2 actions
- at most 3 relevant memories
- relevant known contact for messaging
- extracted value or parsed reminder time when relevant
- risk flag

## Safety behavior

High-risk actions still stay behind confirmation.

Current examples of high-risk behavior:

- payments or transfers
- delete/destructive actions
- formal/official outbound communication
- modifying someone else’s calendar

The stable task flows themselves also include confirmation where it matters:

- send message: confirm before send
- create reminder: confirm before save

## Testing

Run the full unit test suite:

```bash
python -m unittest discover -s tests -v
```

Optional syntax check:

```bash
python -m compileall app tests
```

The tests cover:

- planner outputs for all 3 supported task types
- router decisions for supported, unsupported, high-risk, and replan states
- executor flows for message sending, extract-and-copy, and reminder creation
- context shaping and memory limits
- memory helper retrieval
- contact discovery
- targeting behavior

## Known limitations

- The project is still emulator-first and not tuned for real Android devices yet.
- Chinese text input through `adb shell input text` can be unreliable on some emulator setups.
- The extract-and-copy flow is intentionally bounded; it is not a generic arbitrary information extraction agent.
- The reminder flow is currently optimized around a calendar event/reminder editor path, not every possible Android reminder app.
- UI variations between emulator images can still require page keyword or fallback target tuning in `app/demo_config.py`.

## Next roadmap

- strengthen router logic further with richer replan signals
- integrate a local small model or looped LM for selective replan later
- enrich memory retrieval and contact alias handling later
- add a richer OpenClaw / AgentSkills-compatible skill layer later

