"""Constants for the Switch Control integration."""

DOMAIN = "switch_control"

CONF_SENSOR_ENTITY_ID = "sensor_entity_id"
CONF_OUTPUT_ENTITY_IDS = "output_entity_ids"
CONF_NAME = "name"
CONF_SWITCH_COUNT = "switch_count"
CONF_SWITCHES = "switches"
CONF_LONG_PRESS_ACTION = "long_press_action"
CONF_DOUBLE_PRESS_ACTION = "double_press_action"

DEFAULT_NAME = "Switch Control"
SWITCH_COUNT_OPTIONS = ["1", "2", "4"]

PLATFORMS = ["switch"]

# Long press detection threshold in seconds
LONG_PRESS_THRESHOLD = 0.5

# Double press detection window in seconds
DOUBLE_PRESS_THRESHOLD = 0.4

# Long press action options
LONG_PRESS_ACTION_NONE = "none"
LONG_PRESS_ACTION_TURN_ON = "turn_on"
LONG_PRESS_ACTION_TURN_OFF = "turn_off"
LONG_PRESS_ACTION_TOGGLE = "toggle"
LONG_PRESS_ACTION_OPTIONS = [
    LONG_PRESS_ACTION_NONE,
    LONG_PRESS_ACTION_TURN_ON,
    LONG_PRESS_ACTION_TURN_OFF,
    LONG_PRESS_ACTION_TOGGLE,
]

# Double press action options (same set as long press)
DOUBLE_PRESS_ACTION_NONE = "none"
DOUBLE_PRESS_ACTION_TURN_ON = "turn_on"
DOUBLE_PRESS_ACTION_TURN_OFF = "turn_off"
DOUBLE_PRESS_ACTION_TOGGLE = "toggle"
DOUBLE_PRESS_ACTION_OPTIONS = [
    DOUBLE_PRESS_ACTION_NONE,
    DOUBLE_PRESS_ACTION_TURN_ON,
    DOUBLE_PRESS_ACTION_TURN_OFF,
    DOUBLE_PRESS_ACTION_TOGGLE,
]

# Home Assistant event names fired by this integration
EVENT_BUTTON_PRESSED = f"{DOMAIN}_button_pressed"
EVENT_DOUBLE_PRESS = f"{DOMAIN}_double_press"
EVENT_LONG_PRESS = f"{DOMAIN}_long_press"
EVENT_LONG_PRESS_RELEASED = f"{DOMAIN}_long_press_released"
