"""Config-Flow für Backblaze B2 (fragt Bucket & Keys vom Nutzer ab)."""
from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

DOMAIN = "b2_backup"

CONF_KEY_ID  = "application_key_id"
CONF_KEY     = "application_key"
CONF_BUCKET  = "bucket"
CONF_ENDPOINT = "endpoint"
CONF_PREFIX  = "prefix"

_DEFAULTS = {CONF_ENDPOINT: "production", CONF_PREFIX: "ha-backup"}

class B2ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            ok = await self.hass.async_add_executor_job(_validate_creds, user_input)
            if ok:
                title = f"B2: {user_input[CONF_BUCKET]}"
                return self.async_create_entry(title=title, data=user_input)
            errors["base"] = "auth"

        schema = vol.Schema(
            {
                vol.Required(CONF_KEY_ID): str,
                vol.Required(CONF_KEY): str,
                vol.Required(CONF_BUCKET): str,
                vol.Optional(CONF_ENDPOINT, default=_DEFAULTS[CONF_ENDPOINT]): str,
                vol.Optional(CONF_PREFIX,  default=_DEFAULTS[CONF_PREFIX]):  str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

@callback
def _validate_creds(data: dict) -> bool:
    """Blockierend in Threadpool: prüft, ob Bucket & Schlüssel gültig sind."""
    try:
        from b2sdk.v2 import B2Api, InMemoryAccountInfo
        api = B2Api(InMemoryAccountInfo())
        api.authorize_account(data[CONF_ENDPOINT], data[CONF_KEY_ID], data[CONF_KEY])
        api.get_bucket_by_name(data[CONF_BUCKET])  # wirft bei 404
        return True
    except Exception:  # bewusst breit gefasst → nur 'auth' Error im Flow
        return False
