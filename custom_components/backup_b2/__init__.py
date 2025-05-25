"""Backblaze B2 – Backup-Agent für Home Assistant."""
from __future__ import annotations
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry

DOMAIN = "b2_backup"

async def async_get_backup_agents(hass: HomeAssistant):
    """Von HA aufgerufen, um Agent-Instanzen zu bekommen."""
    from .backup import B2BackupAgent  # lokaler Import
    return [
        B2BackupAgent(hass, entry.data)
        for entry in hass.config_entries.async_entries(DOMAIN)
    ]

async def async_setup(hass: HomeAssistant, _):     # keine YAML nötig
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    @callback
    def _reload(_=None):
        hass.bus.async_fire(f"{DOMAIN}_reload")
    entry.async_on_unload(entry.add_update_listener(_reload))
    _reload()
    return True

async def async_unload_entry(hass: HomeAssistant, _entry):
    return True
