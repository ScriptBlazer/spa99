"""Download the DB-IP "IP to Country Lite" file (CC BY 4.0, no account): this month's, else last month's.
Used by the Docker build and scripts/update_geoip.sh:  python -m common.geoip_fetch <destination.mmdb>
Exit 0 when the file was written, 1 when neither month could be fetched (the caller carries on without it).
Standard library only, so it runs in the image before Django is configured."""
import gzip
import os
import shutil
import sys
import tempfile
import urllib.request
from datetime import date
from pathlib import Path

URL = "https://download.db-ip.com/free/dbip-country-lite-{year}-{month:02d}.mmdb.gz"
TIMEOUT = 60
USER_AGENT = "Mozilla/5.0 (compatible; spa99-geoip-fetch)"  # the host's firewall refuses the bare Python-urllib agent


def candidate_urls(today=None):
    """This month first, then last month."""
    today = today or date.today()
    last = date(today.year - 1, 12, 1) if today.month == 1 else date(today.year, today.month - 1, 1)
    return [URL.format(year=d.year, month=d.month) for d in (today, last)]


def fetch(destination, today=None, opener=urllib.request.urlopen):
    """Write the file to `destination` (atomically). Returns the URL used, or None."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    for url in candidate_urls(today):
        try:
            with opener(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=TIMEOUT) as response, tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as tmp:
                with gzip.GzipFile(fileobj=response) as unzipped:
                    shutil.copyfileobj(unzipped, tmp)
            os.chmod(tmp.name, 0o644)  # NamedTemporaryFile is 0600; the app user is not the one who fetched it (Docker build runs as root)
            Path(tmp.name).replace(destination)
            return url
        except Exception as error:  # noqa: BLE001 - missing month, no network, bad gzip: try the next one
            print(f"GeoIP: could not fetch {url}: {error}", file=sys.stderr)
            try:
                Path(tmp.name).unlink()
            except (NameError, OSError):
                pass
    return None


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "geoip/dbip-country-lite.mmdb"
    used = fetch(target)
    print(f"GeoIP: wrote {target} from {used}" if used else "GeoIP: no file downloaded (countries will show as unknown)")
    sys.exit(0 if used else 1)
