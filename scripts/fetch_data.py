"""Download the organizer's public-link archive without a participant account."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

DATA_URL = "https://drive.google.com/uc?export=download&id=1yHdWaSb6gwPAUrqco-KrwR2U_YhzFQFT"
EXPECTED_SHA256 = "0ce15a932439d076033cba159ca7ede8bf49f188892bb4cc0809b1af49492d72"
FILES = ("nodes.parquet", "edges.parquet", "transactions.parquet")
MAX_ARCHIVE_BYTES = 20_000_000


def fetch(destination: Path, archive: Path | None = None) -> dict:
    if archive:
        payload = archive.read_bytes()
    else:
        request = Request(DATA_URL, headers={"User-Agent": "MoneyGraph-HackAlem/1.0"})
        with urlopen(request, timeout=60) as response:
            payload = response.read(MAX_ARCHIVE_BYTES + 1)
    if len(payload) > MAX_ARCHIVE_BYTES:
        raise ValueError("Архив превышает допустимые 20 MB; проверьте источник вручную.")
    digest = hashlib.sha256(payload).hexdigest()
    if digest != EXPECTED_SHA256:
        raise ValueError(
            f"Версия архива изменилась: SHA-256 {digest}. "
            "Организаторы могли обновить данные; проверьте новый состав перед изменением ожидаемого хеша."
        )
    with ZipFile(io.BytesIO(payload)) as zipped:
        # Read only explicitly named organizer inputs; never extract archive paths.
        contents = {}
        for filename in FILES:
            member = zipped.getinfo(f"data/{filename}")
            if member.file_size > MAX_ARCHIVE_BYTES:
                raise ValueError(f"Слишком большой файл {filename}.")
            content = zipped.read(member)
            if not (content.startswith(b"PAR1") and content.endswith(b"PAR1")):
                raise ValueError(f"{filename} не является Parquet.")
            contents[filename] = content
    destination.mkdir(parents=True, exist_ok=True)
    manifest = {
        "source": DATA_URL,
        "archive_sha256": digest,
        "archive_bytes": len(payload),
        "files": {name: hashlib.sha256(value).hexdigest() for name, value in contents.items()},
        "usage": "Только в рамках HackAlem AI; не публиковать данные в открытом доступе.",
    }
    for filename, content in contents.items():
        with tempfile.NamedTemporaryFile(dir=destination, delete=False) as temporary:
            temporary.write(content)
            temp_path = Path(temporary.name)
        os.replace(temp_path, destination / filename)
    (destination / "source.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=Path("data"))
    parser.add_argument(
        "--archive", type=Path, help="Официальный ZIP, ранее скачанный для офлайн-запуска"
    )
    args = parser.parse_args()
    try:
        manifest = fetch(args.dest, args.archive)
    except (OSError, URLError, ValueError, BadZipFile, KeyError) as error:
        print(f"Не удалось получить данные: {error}", file=sys.stderr)
        return 1
    print(f"Данные сохранены: {args.dest.resolve()}")
    print(f"SHA-256 архива: {manifest['archive_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
