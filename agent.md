# Agent Guide: Switch Control

This document provides context and conventions for AI agents working on the **Switch Control** Home Assistant custom integration.

## Project Overview

**Switch Control** is a [HACS](https://hacs.xyz/) custom integration for [Home Assistant](https://www.home-assistant.io/). It allows **sensor** entities (on/off inputs) to automatically control one or more **output** entities such as lights and switches. It is designed for 2-gang or 4-gang wall panels where each input independently controls its own set of outputs.

- **Domain:** `switch_control`
- **Version:** `1.0.0`
- **IoT Class:** `local_push` (no cloud dependencies)
- **Minimum HA version:** `2023.1.0`
- **Repository:** https://github.com/thomaskaergaard/switch-control

## Repository Structure

```
switch-control/
├── agent.md                          # This file
├── README.md                         # User-facing documentation
├── hacs.json                         # HACS metadata
├── .gitignore
└── custom_components/
    └── switch_control/
        ├── __init__.py               # Integration setup and teardown
        ├── config_flow.py            # Multi-step UI configuration flow
        ├── const.py                  # Shared constants
        ├── switch.py                 # Virtual switch entity implementation
        ├── manifest.json             # Integration metadata
        ├── strings.json              # UI strings (source of truth)
        └── translations/
            └── en.json               # English translations (mirrors strings.json)
```

## Key Files

| File | Purpose |
|------|---------|
| `__init__.py` | Registers the integration, sets up platforms, and tears down on unload |
| `config_flow.py` | Implements the multi-step configuration UI using HA's `ConfigFlow` API |
| `switch.py` | Defines `SwitchControlEntity` — one virtual switch per configured input |
| `const.py` | All shared constants (domain name, config keys, defaults) |
| `manifest.json` | HA integration manifest (domain, version, codeowners, iot_class, etc.) |
| `strings.json` | Source of truth for all UI text used in config flow steps and errors |
| `translations/en.json` | English translation file — must stay in sync with `strings.json` |

## Architecture

### Configuration Flow (Multi-Step)

The integration uses Home Assistant's declarative `ConfigFlow` pattern:

1. **Step 1 (`user`):** User enters a panel name and selects the number of switches (2 or 4).
2. **Steps 2…N (`switch_N`):** For each switch input, the user provides:
   - A friendly name
   - A sensor entity (the input that drives the output)
   - One or more output entities (`light.*` or `switch.*`)

Config entries are stored in `hass.data[DOMAIN][entry.entry_id]`.

### Entity Model

Each configured switch input creates one `SwitchControlEntity` (a virtual `switch` platform entity). Each entity:
- Mirrors the state of its assigned sensor entity
- Controls all assigned output entities (turns them on/off in sync)
- Can be toggled manually, overriding the sensor state
- Listens for sensor state changes via `async_track_state_change_event`

### Backward Compatibility

The code supports both the legacy single-switch format (older config entries) and the current multi-switch format. Do not break legacy entries when making changes.

## Coding Conventions

- **Language:** Python 3, async/await throughout.
- **Prefix conventions:**
  - `CONF_*` — configuration key constants (defined in `const.py`)
  - `async_*` — async functions (required by Home Assistant conventions)
  - `_*` — private/internal methods
- **Logging:** Use the module-level `_LOGGER` (created with `logging.getLogger(__name__)`).
- **No external dependencies:** The integration relies only on Home Assistant core libraries.
- **Non-polling entities:** All entities use `_attr_should_poll = False` and push state updates.
- **Entity names:** Entities use `_attr_has_entity_name = True`.
- **Service calls:** Output entities are controlled via `hass.services.async_call` with dynamic domain detection (`light` or `switch`).

## Adding or Changing UI Text

All user-visible text lives in two places that must stay in sync:

1. `custom_components/switch_control/strings.json`
2. `custom_components/switch_control/translations/en.json`

When you add a new config step, error code, or label, update **both** files.

## No Build or Test Infrastructure

This project has **no automated build, lint, or test pipeline**. There are no `Makefile`, `tox.ini`, `pytest` configurations, or CI workflows. Validation is done manually by loading the integration into a Home Assistant development instance.

When making changes:
- Verify Python syntax is valid (`python -m py_compile <file>`)
- Test by copying `custom_components/switch_control` into a running Home Assistant instance
- Confirm the config flow works end-to-end for both 2-switch and 4-switch configurations
- Confirm legacy config entries still load without errors

## Common Tasks

### Add a new configuration option
1. Add the constant to `const.py`.
2. Add the schema field in `config_flow.py` at the appropriate step.
3. Add the UI label to `strings.json` and `translations/en.json`.
4. Read the value in `switch.py` or `__init__.py` where it is needed.

### Add a new switch count option
1. Update `SWITCH_COUNT_OPTIONS` in `const.py`.
2. Update the `config_flow.py` step selector.
3. Update `README.md` to reflect the new option.

### Add a new translation
1. Update `strings.json` with any new or changed keys (this file is the source of truth).
2. Update `translations/en.json` to mirror `strings.json` with English values.
3. Copy `translations/en.json` to `translations/<language_code>.json`.
4. Translate all string values in the new file (keep keys unchanged).

### Change the integration version
Update the `version` field in `manifest.json`. Use [semantic versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`):
- **PATCH** (`1.0.x`): Bug fixes and minor improvements.
- **MINOR** (`1.x.0`): Backward-compatible new features.
- **MAJOR** (`x.0.0`): Breaking changes.

Releasing is done by triggering the **Release** GitHub Actions workflow (`.github/workflows/release.yml`) manually via `workflow_dispatch`. Select the bump type (`patch`, `minor`, or `major`; default: `patch`). The workflow will:
1. Read the current version from `manifest.json`.
2. Compute the next version according to [semver](https://semver.org/).
3. Write the new version back to `manifest.json` and push a commit to `main`.
4. Create a GitHub release and git tag (e.g. `v1.0.2`).

HACS uses these releases to surface the correct semantic version to users instead of a raw commit SHA.
