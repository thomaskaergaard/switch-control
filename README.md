# Switch Control

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

A [HACS](https://hacs.xyz/) custom integration for [Home Assistant](https://www.home-assistant.io/) that lets **sensor** entities (on/off inputs) automatically control one or more **output** entities such as lamps (lights) and outlets (switches).

## Features

- Support for **2 or 4 independent switch inputs** per integration entry — ideal for 2-gang or 4-gang wall panels.
- Each switch input monitors its own sensor entity and controls its own set of output entities.
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
   - **Number of switches** – choose **2** or **4** depending on how many independent inputs the panel has.
4. **Step 2…N – Configure each switch input** (repeated for each switch):
   - **Name** – a friendly name for this individual switch (e.g. `Ceiling Light`).
   - **Sensor (input)** – the sensor entity whose state drives the outputs.
   - **Outputs (lamps and outlets)** – one or more `light.*` or `switch.*` entities to control.
5. Click **Submit** on each step.

One virtual switch entity is created for every configured input (e.g. `switch.ceiling_light`, `switch.floor_lamp`). Each entity's state mirrors its own sensor and controls its own set of outputs simultaneously.

## How It Works

| Sensor state | Virtual switch | Output entities |
|---|---|---|
| `on`  | `on`  | all turned **on**  |
| `off` | `off` | all turned **off** |

Each virtual switch can also be toggled manually, independently of the sensor, allowing full manual override per channel.

## License

MIT
