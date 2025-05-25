"""Backup-Agent, der TAR-Streams in einen B2-Bucket hochlädt."""
from __future__ import annotations
import asyncio
from collections.abc import AsyncIterator, Callable, Coroutine
from io import BytesIO
from typing import Any

from homeassistant.components.backup import (
    AgentBackup,
    BackupAgent,
    BackupAgentError,
    BackupNotFound,
)
from homeassistant.core import HomeAssistant

from b2sdk.v2 import B2Api, InMemoryAccountInfo, exception as b2e

DOMAIN = "b2_backup"

CONF_KEY_ID = "application_key_id"
CONF_KEY    = "application_key"
CONF_BUCKET = "bucket"
CONF_ENDPOINT = "endpoint"
CONF_PREFIX = "prefix"

class B2BackupAgent(BackupAgent):
    """Implementiert die HA-BackupAgent-Schnittstelle für Backblaze B2."""
    domain = DOMAIN

    def __init__(self, hass: HomeAssistant, cfg: dict[str, Any]) -> None:
        self._loop = hass.loop
        self._key_id   = cfg[CONF_KEY_ID]
        self._key      = cfg[CONF_KEY]
        self._bucket   = cfg[CONF_BUCKET]
        self._endpoint = cfg.get(CONF_ENDPOINT, "production")
        self._prefix   = cfg.get(CONF_PREFIX, "ha-backup")
        self.name      = f"Backblaze B2 ({self._bucket})"
        self.unique_id = f"{DOMAIN}_{self._bucket}"

        info = InMemoryAccountInfo()
        self._api = B2Api(info)
        # Autorisierung in Threadpool, damit der Event-Loop frei bleibt
        hass.async_create_task(
            hass.async_add_executor_job(
                self._api.authorize_account, self._endpoint, self._key_id, self._key
            )
        )
        self._bucket_obj = None

    # interne Hilfe
    def _bucket_handle(self):
        if self._bucket_obj is None:
            self._bucket_obj = self._api.get_bucket_by_name(self._bucket)
        return self._bucket_obj

    # ---------- BackupAgent-Methoden ----------
    async def async_upload_backup(
        self,
        *,
        open_stream: Callable[[], Coroutine[Any, Any, AsyncIterator[bytes]]],
        backup: AgentBackup,
        **_
    ) -> None:
        stream = await open_stream()
        buf = BytesIO()
        async for chunk in stream:
            buf.write(chunk)
        buf.seek(0)
        filename = f"{self._prefix}/{backup.backup_id}.tar"

        def _upload():
            self._bucket_handle().upload_bytes(buf.getvalue(), filename)

        await asyncio.get_running_loop().run_in_executor(None, _upload)

    async def async_list_backups(self, **_) -> list[AgentBackup]:
        def _list():
            out = []
            for fv in self._bucket_handle().ls():
                if fv.file_name.startswith(self._prefix):
                    out.append(
                        AgentBackup(
                            backup_id=fv.id_,
                            name=fv.file_name.rsplit('/', 1)[-1],
                            created=fv.upload_timestamp,
                            size=fv.size,
                        )
                    )
            return out
        return await asyncio.get_running_loop().run_in_executor(None, _list)

    async def async_download_backup(self, backup_id: str, **_) -> AsyncIterator[bytes]:
        def _dl():
            return self._bucket_handle().download_file_by_id(backup_id).read()
        data = await asyncio.get_running_loop().run_in_executor(None, _dl)
        yield data

    async def async_delete_backup(self, backup_id: str, **_):
        def _del():
            try:
                self._bucket_handle().delete_file_version(backup_id, None)
            except b2e.B2Error as err:
                raise BackupNotFound from err
        await asyncio.get_running_loop().run_in_executor(None, _del)
