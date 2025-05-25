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
from homeassistant.core import HomeAssistant, callback

from b2sdk.v2 import B2Api, InMemoryAccountInfo, exception as b2e

from . import DOMAIN, CONF_KEY_ID, CONF_KEY, CONF_BUCKET, CONF_PREFIX

# -- listener bookkeeping -------------------------------------------------
_DATA_LISTENERS = f"{DOMAIN}_listeners"

@callback
def async_register_backup_agents_listener(
    hass: HomeAssistant, *, listener: Callable[[], None], **kwargs: Any
) -> Callable[[], None]:
    hass.data.setdefault(_DATA_LISTENERS, []).append(listener)

    @callback
    def _remove() -> None:
        hass.data[_DATA_LISTENERS].remove(listener)

    return _remove


async def async_get_backup_agents(hass: HomeAssistant) -> list[BackupAgent]:
    """Return one agent per YAML section."""
    confs: list[dict[str, Any]] = hass.data.get(DOMAIN, [])
    if isinstance(confs, dict):  # single block → wrap in list
        confs = [confs]
    return [B2BackupAgent(hass, c) for c in confs]


# ------------------------------------------------------------------------
class B2BackupAgent(BackupAgent):

    domain = DOMAIN

    def __init__(self, hass: HomeAssistant, cfg: dict[str, Any]) -> None:
        self._loop = hass.loop
        self._key_id   = cfg[CONF_KEY_ID]    """Backblaze B2 implementation of the BackupAgent protocol."""

        info = InMemoryAccountInfo()
        api  = B2Api(info)
        # authorise is blocking – run once here in executor
        if not hass.is_running:
            api.authorize_account("production", self._key_id, self._key)
        else:
            # ensure start-up doesn’t stall the event-loop
            hass.async_create_task(
                hass.async_add_executor_job(
                    api.authorize_account, "production", self._key_id, self._key
                )
            )
        self._api    = api
        self._bucket_obj = None  # lazy

    # small helper --------------------------------------------------------
    def _bucket_handle(self):
        if self._bucket_obj is None:
            self._bucket_obj = self._api.get_bucket_by_name(self._bucket)
        return self._bucket_obj

    # required interface --------------------------------------------------
    async def async_upload_backup(
        self,
        *,
        open_stream: Callable[[], Coroutine[Any, Any, AsyncIterator[bytes]]],
        backup: AgentBackup,
        **kwargs: Any,
    ) -> None:
        """Read the tar stream and push to B2."""
        stream = await open_stream()
        buf = BytesIO()
        async for chunk in stream:
            buf.write(chunk)
        buf.seek(0)

        filename = f"{self._prefix}/{backup.backup_id}.tar"

        def _upload() -> None:  # blocking in thread-pool
            self._bucket_handle().upload_bytes(buf.getvalue(), filename)

        await asyncio.get_running_loop().run_in_executor(None, _upload)

    # ─ optional but nice to have ────────────────────────────────────────
    async def async_list_backups(self, **kwargs: Any) -> list[AgentBackup]:
        def _list() -> list[AgentBackup]:
            out: list[AgentBackup] = []
            for file_version in self._bucket_handle().ls():
                if not file_version.file_name.startswith(self._prefix):
                    continue
                out.append(
                    AgentBackup(
                        backup_id=file_version.id_,
                        name=file_version.file_name.rsplit("/", 1)[-1],
                        created=file_version.upload_timestamp,
                        size=file_version.size,
                    )
                )
            return out

        return await asyncio.get_running_loop().run_in_executor(None, _list)

    async def async_download_backup(
        self, backup_id: str, **kwargs: Any
    ) -> AsyncIterator[bytes]:
        """Stream down a backup."""
        def _download() -> bytes:
            return self._bucket_handle().download_file_by_id(backup_id).read()

        data = await asyncio.get_running_loop().run_in_executor(None, _download)
        yield data  # single-chunk iterator

    async def async_delete_backup(self, backup_id: str, **kwargs: Any) -> None:
        def _delete() -> None:
            try:
                self._bucket_handle().delete_file_version(backup_id, None)
            except b2e.B2Error as err:
                raise BackupNotFound from err
        await asyncio.get_running_loop().run_in_executor(None, _delete)
