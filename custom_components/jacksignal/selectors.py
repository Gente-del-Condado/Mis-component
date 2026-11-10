"""Use Home Assistant's native controls for both languages and themes."""

try:
    import probatio as validation
except ModuleNotFoundError:
    # Older Home Assistant releases use Voluptuous for the same form API.
    import voluptuous as validation

from homeassistant.helpers import selector

from .const import Priority


def media_selector() -> selector.MediaSelector:
    return selector.MediaSelector({"accept": ["audio/*"]})


def priority_selector() -> selector.SelectSelector:
    return selector.SelectSelector({
        "options": [priority.name.lower() for priority in Priority],
        "translation_key": "priority",
        "mode": selector.SelectSelectorMode.DROPDOWN,
    })
