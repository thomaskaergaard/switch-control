# Switch Control

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

A [HACS](https://hacs.xyz/) custom integration for [Home Assistant](https://www.home-assistant.io/) that lets a **sensor** entity (on/off input) automatically control one or more **output** entities such as lamps (lights) and outlets (switches).

## Features

- Monitor any binary sensor or sensor entity for `on`/`off` state changes.
- Automatically turn on/off any number of `light` or `switch` entities (lamps, outlets, etc.).
- The controller itself is exposed as a virtual switch in Home Assistant, so you can also toggle it manually from the UI or automations.
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
3. Fill in the form:
   - **Name** – a friendly name for this controller (e.g. `Living Room Lamps`).
   - **Sensor (input)** – the sensor entity whose state drives the outputs (e.g. `sensor.motion_detector`).
   - **Outputs (lamps and outlets)** – one or more `light.*` or `switch.*` entities to control (e.g. `light.living_room`, `switch.outlet_1`).
4. Click **Submit**.

A new switch entity (e.g. `switch.living_room_lamps`) will appear in Home Assistant. Its state mirrors the sensor and it controls all configured outputs simultaneously.

## How It Works

| Sensor state | Controller switch | Output entities |
|---|---|---|
| `on`  | `on`  | all turned **on**  |
| `off` | `off` | all turned **off** |

The virtual switch can also be toggled manually, independently of the sensor, allowing full manual override.

## License

MIT
