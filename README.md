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
- `axoliot.read_live` – élő olvasás a Matter szerverről wildcarddal (`*/*/*`), a gyorsítótárat megkerülve; az ismeretlen (gyártói) clustereket is megmutatja.
- `axoliot.write_attribute` – attribútum írása `endpoint/cluster/attribute` úton (pl. `1/6/16387` = StartUpOnOff).

### Melegvíz-hőszivattyú COP (szenzorok)
Hőszivattyús melegvíz-tárolók látszólagos COP-ja fűtési ciklusonként, olyan gyártói
integrációkhoz, amelyek periódusonként (pl. 2 óránként) egy fogyasztási értéket adnak
(`state_class: total`, `last_reset` ablakonként).

Beállítás: Beállítások → Eszközök és szolgáltatások → Axoliot → **Konfigurálás**:
- tartály hőmérséklete (`water_heater` entitás `current_temperature` attribútuma vagy hőmérséklet szenzor),
- hőszivattyú fogyasztása periódusonként (kWh), opcionálisan a fűtőszálé is,
- opcionálisan külső / beszívott levegő hőmérséklete,
- tartály térfogata (liter).

Működés:
- Ciklus: amíg bármelyik fogyasztási ablak a küszöb (0,02 kWh) fölött van; az első üresjárati ablak zárja le.
- Leadott hő = (T_max − T_min) × térfogat × 1,163 Wh/(l·K); COP = leadott hő / (hőszivattyú + fűtőszál kWh).
- A kezdőhőmérséklet az első fűtő ablak alatti minimum (a recorder előzményeiből is, így egy
  újraindítás után is pontos). A futó ciklus állapota újraindítás után visszaáll.
- A hőszivattyú és a fűtőszál egyszerre érkező ablakértékét együtt dolgozza fel.

Entitások (a „Melegvíz hőszivattyú” eszköz alatt):
- **COP** – az utolsó lezárt ciklusé; attribútumokban a futó (`cycle_*`) és az utolsó (`last_*`) ciklus adatai.
- **Ciklus külső átlag** – a külső hőmérséklet átlaga az utolsó ciklus alatt.

A COP *látszólagos*: a ciklus alatti vízvételt nem látja (ilyenkor alulbecsül), és a tartályt
egyetlen hőmérsékletpont alapján, egyenletesen átfűtöttnek tekinti.

## Fejlesztés
Új modul: új `custom_components/axoliot/<modul>.py`, regisztráció az `__init__.py`-ban (szolgáltatás)
vagy egy platformon keresztül (entitások).

Tesztek (Home Assistant nélkül futnak): `python -m unittest discover -s tests`
