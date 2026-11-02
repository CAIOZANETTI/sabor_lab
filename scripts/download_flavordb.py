"""Baixa os ingredientes (entidades) do FlavorDB2, um JSON por ingrediente.

Fonte: https://cosylab.iiitd.edu.in/flavordb2/  (CosyLab, IIIT-Delhi)
Licença dos dados: CC BY-NC-SA 3.0 (uso não comercial, com atribuição).

Cada entidade traz o ingrediente (nome, categoria, nome científico) e a lista
de moléculas de sabor com propriedades físico-químicas e descritores de
odor/sabor. O download é educado: uma requisição por segundo e retomável
(arquivos já baixados são pulados).

Uso:
    python scripts/download_flavordb.py            # ids 1..1100
    python scripts/download_flavordb.py --start 1 --end 1100 --delay 1.0
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "https://cosylab.iiitd.edu.in/flavordb2/entities_json?id={}"
ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "raw" / "flavordb" / "entities"


def fetch(entity_id: int, timeout: float = 60.0) -> dict | None:
    """Retorna o JSON da entidade ou None se o id não existir (404)."""
    try:
        with urllib.request.urlopen(BASE_URL.format(entity_id), timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return None
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=1100)
    parser.add_argument("--delay", type=float, default=1.0, help="segundos entre requisições")
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = missing = skipped = 0

    for entity_id in range(args.start, args.end + 1):
        out = OUT_DIR / f"{entity_id}.json"
        if out.exists():
            skipped += 1
            continue

        for attempt in range(1, args.retries + 1):
            try:
                data = fetch(entity_id)
                break
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as err:
                print(f"id={entity_id} tentativa {attempt} falhou: {err}")
                time.sleep(args.delay * 2**attempt)
        else:
            print(f"id={entity_id} desistindo após {args.retries} tentativas")
            continue

        if data is None:
            missing += 1
        else:
            out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            ok += 1
            print(f"id={entity_id} {data.get('entity_alias_readable')!r} "
                  f"({len(data.get('molecules', []))} moléculas)")
        time.sleep(args.delay)

    print(f"\nconcluído: {ok} baixados, {skipped} já existiam, {missing} ids inexistentes")


if __name__ == "__main__":
    main()
