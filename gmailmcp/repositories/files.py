"""Utilidades de E/S de archivos compartidas por los repositorios."""
import json
import os
import tempfile


def write_text_atomic(path: str, text: str) -> None:
    """Escribe en un temporal y lo renombra: nunca deja el archivo a medio escribir."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp_", suffix=os.path.basename(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def read_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json_atomic(path: str, data) -> None:
    write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2))
