"""Regenerate common/data/countries.json (the country select for mobile numbers): `.venv/bin/python scripts/make_countries.py`.
Run it only when the `phonenumbers` library is upgraded. It needs phonenumbers' geocoder data (about 100 MB of memory), which is the
reason the list is committed instead of built when the site starts."""
import json
from pathlib import Path

import phonenumbers
from phonenumbers import geocoder

EXTRA_NAMES = {"XK": "Kosovo", "AC": "Ascension Island", "TA": "Tristan da Cunha", "CP": "Clipperton Island"}

found = []
for iso in sorted(phonenumbers.SUPPORTED_REGIONS):
    example = phonenumbers.example_number(iso)
    name = (geocoder.country_name_for_number(example, "en") if example else "") or EXTRA_NAMES.get(iso, "")
    if name:
        found.append({"iso": iso, "dial": f"+{phonenumbers.country_code_for_region(iso)}", "name": name})
target = Path(__file__).resolve().parent.parent / "common" / "data" / "countries.json"
target.write_text(json.dumps(found, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
print(f"{len(found)} countries written to {target}")
