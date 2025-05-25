 ""Setup & Config-Entry-Lifecycle für b2_backup."""
from __future__ import annotations
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .backup import async_on_config_entry_changed, DOMAIN

async def async_setup(_hass: HomeAssistant, _config):
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    # Listener informieren, sobald dieser Eintrag geladen / geändert wird
    entry.async_on_unload(
        entry.add_update_listener(
            lambda *_: async_on_config_entry_changed(hass)
        )
    )
    async_on_config_entry_changed(hass)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    async_on_config_entry_changed(hass)
    return True
