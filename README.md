# axoliot-hacs

Saját Home Assistant kiegészítések egyetlen HACS-integrációban (`axoliot`).

## Telepítés
1. HACS → ⋮ → Egyéni tárolók → ennek a repónak az URL-je, kategória: Integráció.
2. Letöltés, HA újraindítás.
3. Beállítások → Eszközök és szolgáltatások → Integráció hozzáadása → **Axoliot**.

## Modulok

### Matter (`axoliot.*` szolgáltatások)
Szabványos Matter attribútumok és parancsok, amiket a core Matter integráció nem tesz ki entitásként. A core Matter-kliensét használja.
- `axoliot.timed_on` – időzített bekapcsolás (`OnWithTimedOff`), másodpercben.
- `axoliot.read_attributes` – node attribútumok olvasása (válaszként), opcionálisan cluster szerint.
- `axoliot.write_attribute` – attribútum írása `endpoint/cluster/attribute` úton (pl. `1/6/16387` = StartUpOnOff).

Új modul hozzáadása: új `custom_components/axoliot/<modul>.py`, regisztráció az `__init__.py`-ban.
