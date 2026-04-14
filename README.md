# Android GUI Agent MVP

This repository contains a small Android GUI agent MVP focused on one stable demo: open the system messages app in an Android emulator, find a contact, and send a template message with manual confirmation before send.

## What is implemented

- `app/utils/adb.py`: low-level ADB wrapper with device selection, tap, swipe, input, screenshot, focus, screen size, and UI XML dump.
- `app/state.py`: minimal execution state for task, page, recent actions, screenshots, and replan flag.
- `app/skills/`: atomic skills for app open, tap, swipe, text input, back, wait, screen read, confirmation, and in-app search.
- `app/planner.py`: rule-based planner for the MVP demo flow, with optional OpenAI-backed JSON planning.
- `app/executor.py`: step execution, screenshots, logging, expectation checks, one recovery attempt, and SQLite success/failure recording.
- `app/demo_runner.py`: a quick entry point for the fixed SMS demo.

## Environment

- Python 3.8+ is supported in the current codebase.
- Android Studio Emulator must be running.
- `adb devices` must show a connected emulator.
- The current demo assumes the emulator uses the default Android messages app package: `com.google.android.apps.messaging`.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Check the emulator:

```bash
adb devices
python -m app.utils.test_actions
```

## Run the fixed SMS demo

Use the quick demo runner:

```bash
python -m app.demo_runner --contact 张三 --message-text "我晚点到"
```

Or use the generic CLI entry:

```bash
python -m app.main --task "给张三发消息 \"我晚点到\""
```

## How the demo works

1. Open the system messages app.
2. Read the screen and classify the page.
3. Find the search entry point with semantic matching.
4. Search for the contact.
5. Tap the contact result.
6. Focus the message input.
7. Type the template message.
8. Ask for manual confirmation.
9. Tap send.

The executor first tries semantic UI target matching from the dumped XML. On known stable pages, it can fall back to ratio-based coordinates configured in `app/demo_config.py`.

## Logs, screenshots, and memory

- Logs are written to `data/logs/agent.log`
- Screenshots are written to `data/screenshots/<task_name>/`
- SQLite memory is written to `data/memory.db`

Each step logs:

- action name
- success or failure
- detail
- screenshot path
- page
- target
- whether fallback coordinates were used

## Testing

Run the test suite with the Python standard library:

```bash
python -m unittest discover -s tests -v
```

The suite covers:

- planner output for the demo flow
- target matching priority and fallback coordinate scaling
- context trimming
- executor integration with a mock ADB device
- success and failure trajectory recording
