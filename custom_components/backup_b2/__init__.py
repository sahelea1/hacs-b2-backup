"""Backblaze B2 – Backup-Agent für Home Assistant."""
from __future__ import annotations
from typing import Any, Callable
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry

DOMAIN = "b2_backup"
_DATA_LISTENERS = f"{DOMAIN}_listeners"          # ← neu

# ───────────────── Backup-Schnittstelle ────────────────────────────────
async def async_get_backup_agents(hass: HomeAssistant):
    """Von HA aufgerufen, um aktuelle Agenten zu holen."""
    from .backup import B2BackupAgent
    # nur geladene Config-Einträge
    return [
        B2BackupAgent(hass, entry.data)
        for entry in hass.config_entries.async_loaded_entries(DOMAIN)
    ]


@callback                                               # ← neu
def async_register_backup_agents_listener(              # ← neu
    hass: HomeAssistant,
    *,
    listener: Callable[[], None],
    **kwargs: Any,
) -> Callable[[], None]:
    """Backup-UI meldet sich hier, um über Änderungen informiert zu werden."""
    hass.data.setdefault(_DATA_LISTENERS, []).append(listener)

    @callback
    def _remove() -> None:
        hass.data[_DATA_LISTENERS].remove(listener)

    return _remove
# ───────────────────────────────────────────────────────────────────────

async def async_setup(hass: HomeAssistant, _):
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    # beim (Re-)Laden des Eintrags alle registrierten Zuhörer informieren
    @callback
    def _notify() -> None:
        for cb in hass.data.get(_DATA_LISTENERS, []):
            cb()

    entry.async_on_unload(entry.add_update_listener(lambda *_: _notify()))
    _notify()
    return True

async def async_unload_entry(hass: HomeAssistant, _entry):
    return True
