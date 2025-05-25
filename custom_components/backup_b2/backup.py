from homeassistant.config_entries import ConfigEntryState
from __future__ import annotations
import asyncio
from collections.abc import AsyncIterator, Callable, Coroutine
from io import BytesIO
from typing import Any, Callable as CB

from homeassistant.components.backup import (
    AgentBackup,
    BackupAgent,
    BackupNotFound,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from b2sdk.v2 import B2Api, InMemoryAccountInfo, exception as b2e

DOMAIN = "b2_backup"
DATA_LISTENERS = f"{DOMAIN}_listeners"

# ───────────── BackupAgent-Implementierung ──────────────────────────────
CONF_KEY_ID  = "application_key_id"
CONF_KEY     = "application_key"
CONF_BUCKET  = "bucket"
CONF_ENDPOINT = "endpoint"
CONF_PREFIX  = "prefix"


class B2BackupAgent(BackupAgent):
    """Uploadet TAR-Streams in einen Backblaze-B2-Bucket."""
    domain = DOMAIN

    def __init__(self, hass: HomeAssistant, cfg: dict[str, Any]) -> None:
        self._loop      = hass.loop
        self._key_id    = cfg[CONF_KEY_ID]
        self._key       = cfg[CONF_KEY]
        self._bucket    = cfg[CONF_BUCKET]
        self._endpoint  = cfg.get(CONF_ENDPOINT, "production")
        self._prefix    = cfg.get(CONF_PREFIX, "ha-backup")
        self.name       = f"Backblaze B2 ({self._bucket})"
        self.unique_id  = f"{DOMAIN}_{self._bucket}"

        info = InMemoryAccountInfo()
        self._api = B2Api(info)
        hass.async_create_task(
            hass.async_add_executor_job(
                self._api.authorize_account,
                self._endpoint,
                self._key_id,
                self._key,
            )
        )
        self._bucket_obj = None

    # ---------- intern ---------------------------------------------------
    def _bucket(self):
        if self._bucket_obj is None:
            self._bucket_obj = self._api.get_bucket_by_name(self._bucket)
        return self._bucket_obj

    # ---------- BackupAgent-API ------------------------------------------
    async def async_upload_backup(
        self,
        *,
        open_stream: Callable[[], Coroutine[Any, Any, AsyncIterator[bytes]]],
        backup: AgentBackup,
        **_kwargs,
    ) -> None:
        stream = await open_stream()
        buf = BytesIO()
        async for chunk in stream:
            buf.write(chunk)
        buf.seek(0)
        filename = f"{self._prefix}/{backup.backup_id}.tar"

        await asyncio.get_running_loop().run_in_executor(
            None, lambda: self._bucket().upload_bytes(buf.getvalue(), filename)
        )

    async def async_list_backups(self, **_) -> list[AgentBackup]:
        def _ls():
            result = []
            for fv in self._bucket().ls():
                if fv.file_name.startswith(self._prefix):
                    result.append(
                        AgentBackup(
                            backup_id=fv.id_,
                            name=fv.file_name.rsplit("/", 1)[-1],
                            created=fv.upload_timestamp,
                            size=fv.size,
                        )
                    )
            return result

        return await asyncio.get_running_loop().run_in_executor(None, _ls)

    async def async_download_backup(
        self, backup_id: str, **_
    ) -> AsyncIterator[bytes]:
        data = await asyncio.get_running_loop().run_in_executor(
            None, lambda: self._bucket().download_file_by_id(backup_id).read()
        )
        yield data

    async def async_delete_backup(self, backup_id: str, **_):
        def _delete():
            try:
                self._bucket().delete_file_version(backup_id, None)
            except b2e.B2Error as err:
                raise BackupNotFound from err

        await asyncio.get_running_loop().run_in_executor(None, _delete)


# ───────────── Hooks, die der Core aufruft  ─────────────────────────────
async def async_get_backup_agents(hass: HomeAssistant):
    """Gibt alle aktiven Agent-Instanzen zurück."""
    return [
        B2BackupAgent(hass, entry.data)
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]


@callback
def async_register_backup_agents_listener(
    hass: HomeAssistant,
    *,
    listener: CB[[], None],
    **_kwargs,
):
    """Backup-UI meldet sich hier; wir speichern den Callback."""
    hass.data.setdefault(DATA_LISTENERS, []).append(listener)

    @callback
    def _remove():
        hass.data[DATA_LISTENERS].remove(listener)

    return _remove


# ───────────── Helfer: Listener nach Änderungen informieren ─────────────
def _notify_listeners(hass: HomeAssistant) -> None:
    for cb in hass.data.get(DATA_LISTENERS, []):
        cb()


# Dieser Helper wird von __init__.py aufgerufen,
# sobald ein Config-Eintrag geladen / aktualisiert / entfernt wird.
def async_on_config_entry_changed(hass: HomeAssistant):
    _notify_listeners(hass)
