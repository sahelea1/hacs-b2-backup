# ─────────────────────────────────────────────────────────────
# custom_components/b2_backup/__init__.py
# ─────────────────────────────────────────────────────────────
"""Setup & Config-Entry-Lifecycle für b2_backup."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .backup import DOMAIN, async_on_config_entry_changed


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Backblaze B2 Backup component."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Backblaze B2 Backup from a config entry."""
    # Register listener for config entry changes
    entry.async_on_unload(
        entry.add_update_listener(
            lambda *_: async_on_config_entry_changed(hass)
        )
    )
    
    # Notify that backup agents may have changed
    async_on_config_entry_changed(hass)
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Notify that backup agents may have changed
    async_on_config_entry_changed(hass)
    return True
