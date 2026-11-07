"""Matter modul: szabványos Matter attribútumok és parancsok, amiket a core nem tesz ki."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
_LOGGER = logging.getLogger(__name__)

# Az On/Off cluster OnTime/OffWaitTime értékei 1/10 másodpercben értendők.
ONOFF_TIME_UNIT_PER_SECOND = 10

TIMED_ON_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Required("on_time"): vol.All(vol.Coerce(float), vol.Range(min=0, max=6500)),
        vol.Optional("off_wait_time", default=0): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=6500)
        ),
        vol.Optional("endpoint", default=1): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=255)
        ),
    }
)
READ_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Optional("cluster"): vol.All(vol.Coerce(int), vol.Range(min=0)),
    }
)
READ_LIVE_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Optional("attribute_path", default="*/*/*"): vol.Match(
            r"^(\d+|\*)/(\d+|\*)/(\d+|\*)$"
        ),
    }
)
WRITE_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Required("attribute_path"): vol.Match(r"^\d+/\d+/\d+$"),
        vol.Required("value"): object,
    }
)


def _jsonable(value: Any) -> Any:
    """Bináris és egyéb nem JSON-barát értékek átalakítása a válaszhoz."""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).hex()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _resolve(hass: HomeAssistant, device_id: str):
    """Return (matter_client, node) for an HA device id."""
    # A core Matter integráció belső segédei, ezért importálunk késve.
    from homeassistant.components.matter.helpers import (  # noqa: PLC0415
        MissingNode,
        get_matter,
        node_from_ha_device_id,
    )

    try:
        node = node_from_ha_device_id(hass, device_id)
        client = get_matter(hass).matter_client
    except (MissingNode, IndexError) as err:
        raise ServiceValidationError(f"Ismeretlen vagy nem Matter eszköz: {device_id}") from err
    if node is None:
        raise ServiceValidationError(f"Nem található Matter node a következőhöz: {device_id}")
    return client, node


def async_register_services(hass: HomeAssistant) -> None:
    """Szolgáltatások regisztrálása."""

    async def timed_on(call: ServiceCall) -> None:
        from chip.clusters import Objects as clusters  # noqa: PLC0415

        client, node = _resolve(hass, call.data["device_id"])
        command = clusters.OnOff.Commands.OnWithTimedOff(
            onOffControl=0,
            onTime=round(call.data["on_time"] * ONOFF_TIME_UNIT_PER_SECOND),
            offWaitTime=round(call.data["off_wait_time"] * ONOFF_TIME_UNIT_PER_SECOND),
        )
        try:
            await client.send_device_command(
                node_id=node.node_id,
                endpoint_id=call.data["endpoint"],
                command=command,
            )
        except Exception as err:  # matter_server hibatípusok változhatnak
            raise HomeAssistantError(f"OnWithTimedOff sikertelen: {err}") from err

    async def read_attributes(call: ServiceCall) -> dict[str, Any]:
        _, node = _resolve(hass, call.data["device_id"])
        cluster = call.data.get("cluster")
        attrs = {
            path: value
            for path, value in node.attributes.items()
            if cluster is None or path.split("/")[1] == str(cluster)
        }
        return {"node_id": node.node_id, "attributes": attrs}

    async def read_live(call: ServiceCall) -> dict[str, Any]:
        """Élő olvasás a Matter szerverről (wildcard), a gyorsítótárat megkerülve."""
        client, node = _resolve(hass, call.data["device_id"])
        path = call.data["attribute_path"]
        try:
            result = await client.read_attribute(node.node_id, path)
        except Exception as err:
            # Egyes szerververziók nem fogadják el a végpont-wildcardot: végpontonként újra.
            if not path.startswith("*"):
                raise HomeAssistantError(f"Élő olvasás sikertelen: {err}") from err
            _LOGGER.debug("Wildcard olvasás hibás (%s), végpontonként próbálom", err)
            result = {}
            rest = path.split("/", 1)[1]
            for endpoint_id in node.endpoints:
                try:
                    result.update(
                        await client.read_attribute(node.node_id, f"{endpoint_id}/{rest}")
                    )
                except Exception as ep_err:
                    result[f"{endpoint_id}/error"] = str(ep_err)
        return {"node_id": node.node_id, "attributes": _jsonable(result)}

    async def write_attribute(call: ServiceCall) -> None:
        client, node = _resolve(hass, call.data["device_id"])
        try:
            await client.write_attribute(
                node_id=node.node_id,
                attribute_path=call.data["attribute_path"],
                value=call.data["value"],
            )
        except Exception as err:
            raise HomeAssistantError(f"Attribútum írása sikertelen: {err}") from err

    hass.services.async_register(DOMAIN, "timed_on", timed_on, schema=TIMED_ON_SCHEMA)
    hass.services.async_register(
        DOMAIN,
        "read_attributes",
        read_attributes,
        schema=READ_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        "read_live",
        read_live,
        schema=READ_LIVE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(DOMAIN, "write_attribute", write_attribute, schema=WRITE_SCHEMA)




def async_remove_services(hass: HomeAssistant) -> None:
    """Matter szolgáltatások eltávolítása."""
    for service in ("timed_on", "read_attributes", "read_live", "write_attribute"):
        hass.services.async_remove(DOMAIN, service)
