# Switch Control

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

A [HACS](https://hacs.xyz/) custom integration for [Home Assistant](https://www.home-assistant.io/) that lets **sensor** entities (on/off inputs) automatically control one or more **output** entities such as lamps (lights) and outlets (switches).

## Features

- Support for **1, 2, or 4 independent switch inputs** per integration entry — ideal for 1-gang, 2-gang, or 4-gang wall panels.
- Each switch input monitors its own sensor entity and controls its own set of output entities.
- **Toggle on press** — a momentary press (sensor briefly on then off) toggles the output state. The first press turns outputs on; the next press turns them off.
- **Double press detection** — two presses within 0.4 seconds fire a `switch_control_double_press` event and can optionally apply a built-in action to the output entities.
- **Long press detection** — holding the input for 0.5 s or longer fires Home Assistant bus events that you can trigger automations from (e.g. dimming a light).
- All virtual switch entities belonging to the same panel are **grouped under a single device** in the Home Assistant device registry for a cleaner UI.
- The controller exposes one virtual switch entity per input, so you can also toggle each one manually from the UI or automations.
- Fully configurable through the Home Assistant UI (no YAML required).

## Installation

### Via HACS (recommended)

1. Open HACS in your Home Assistant instance.
2. Go to **Integrations** → click the three-dot menu → **Custom repositories**.
3. Add `https://github.com/thomaskaergaard/switch-control` with category **Integration**.
4. Search for **Switch Control** and click **Download**.
5. Restart Home Assistant.

### Manual

1. Copy the `custom_components/switch_control` folder into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Switch Control** and click it.
3. **Step 1 – Panel setup:**
   - **Name** – a friendly name for this panel (e.g. `Living Room Panel`).
   - **Number of switches** – choose **1**, **2**, or **4** depending on how many independent inputs the panel has.
4. **Step 2…N – Configure each switch input** (repeated for each switch):
   - **Name** – a friendly name for this individual switch (e.g. `Ceiling Light`).
   - **Sensor (input)** – the sensor entity whose state drives the outputs.
   - **Press outputs (lamps and outlets)** – one or more `light.*` or `switch.*` entities to control on a short press. Also used as the fallback for long press and double press when their specific output lists are empty.
   - **Long press action** – what the integration should do with the outputs when the button is held for 0.5 s or longer (see [Long press / hold](#long-press--hold) below).
   - **Long press outputs (lamps and outlets)** – one or more `light.*` or `switch.*` entities to control on a long press or hold. Leave empty to use the press outputs.
   - **Double press action** – what the integration should do with the outputs when the button is pressed twice within 0.4 s (see [Double press](#double-press) below).
   - **Double press outputs (lamps and outlets)** – one or more `light.*` or `switch.*` entities to control on a double press. Leave empty to use the press outputs.
5. Click **Submit** on each step.

One virtual switch entity is created for every configured input (e.g. `switch.ceiling_light`, `switch.floor_lamp`). Each entity's state mirrors its own sensor and controls its own set of outputs simultaneously. All entities for the same panel are grouped under a single device.

## How It Works

### Short press (toggle)

A momentary press fires the sensor briefly (`on` → `off`). Instead of mirroring the sensor state (which would cause outputs to flicker), the integration **toggles** the output on every press:

| Press | Virtual switch (before) | Virtual switch (after) | Output entities |
|---|---|---|---|
| 1st press | `off` | `on` | all turned **on** |
| 2nd press | `on` | `off` | all turned **off** |

### Double press

When the sensor is triggered twice within **0.4 seconds**, the integration detects a double press:

- The `switch_control_double_press` event is fired on the Home Assistant event bus.
- The configurable **Double press action** is applied to the output entities.

When no double press action is configured, both presses toggle the virtual switch state (the net result is that the state returns to what it was before the double press). When a **Double press action** is set to **Toggle**, the outputs are toggled exactly once from the state they were in before the first press. This means the final output matches what a single press would produce.

### Long press and hold

When the sensor stays `on` for **0.5 seconds or longer**, the integration fires the following [Home Assistant events](https://www.home-assistant.io/docs/configuration/events/) on the event bus and optionally performs a built-in action on the configured output entities:

| Event | When fired | Event data |
|---|---|---|
| `switch_control_button_pressed` | Immediately on every press | `entity_id` |
| `switch_control_double_press` | When a second press is detected within 0.4 s | `entity_id` |
| `switch_control_long_press` | After 0.5 s of holding | `entity_id` |
| `switch_control_hold` | Repeatedly every 0.5 s while the button remains held after the long-press threshold | `entity_id` |
| `switch_control_long_press_released` | When the button is released after a long press | `entity_id` |

The `switch_control_long_press` event fires **once** when the threshold is first reached and applies the configured long press action. The `switch_control_hold` event then fires **repeatedly every 0.5 s** for as long as the button is held, making it ideal for continuous actions such as dimming. `switch_control_long_press_released` fires when the button is finally released.

#### Configurable double press action

The **Double press action** setting (configured per switch input) lets you choose what the integration does with the output entities when a double press is detected:

| Option | Behaviour |
|---|---|
| **None (fire event only)** | No direct output action — only the `switch_control_double_press` event is fired. Use this when you want to handle the double press entirely through automations. |
| **Turn on** | Turns all configured outputs **on** when a double press is detected. |
| **Turn off** | Turns all configured outputs **off** when a double press is detected. |
| **Toggle** | Toggles all configured outputs once from their state before the first press when a double press is detected. |

#### Configurable long press action

The **Long press action** setting (configured per switch input) lets you choose what the integration does with the output entities when a long press is detected:

| Option | Behaviour |
|---|---|
| **None (fire event only)** | No direct output action — only the events above are fired. Use this when you want to handle the long press entirely through automations. |
| **Turn on** | Turns all configured outputs **on** when the long press threshold is reached. |
| **Turn off** | Turns all configured outputs **off** when the long press threshold is reached. |
| **Toggle** | Toggles all configured outputs once from their state before the first press when the long press threshold is reached. |
| **Dim up** | Repeatedly increases the brightness of all configured `light` entities by 10 % every 0.3 s while the button is held. Stops when the button is released. |
| **Dim down** | Repeatedly decreases the brightness of all configured `light` entities by 10 % every 0.3 s while the button is held. Stops when the button is released. |

Events are always fired regardless of the action settings, so you can combine a built-in action with automation logic if needed.

You can listen for these events in automations to implement advanced behaviours such as dimming a light while the button is held:

```yaml
automation:
  - alias: "Dim while holding"
    trigger:
      - platform: event
        event_type: switch_control_hold
        event_data:
          entity_id: switch.ceiling_light
    action:
      - service: light.turn_on
        target:
          entity_id: light.ceiling
        data:
          brightness_step_pct: -10
```

Or trigger a scene on double press:

```yaml
automation:
  - alias: "Scene on double press"
    trigger:
      - platform: event
        event_type: switch_control_double_press
        event_data:
          entity_id: switch.ceiling_light
    action:
      - service: scene.turn_on
        target:
          entity_id: scene.movie_mode
```

Each virtual switch can also be toggled manually, independently of the sensor, allowing full manual override per channel.

## License

MIT
