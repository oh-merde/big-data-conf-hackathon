#!/usr/bin/env python3
"""
Create a simple numpy-backed vector store from the vulnerabilities CSV.

Behavior:
- Reads `utils/data/vulnerabilities_npm_pypi_lean.csv` (or the path passed)
- Splits rows into two CSVs by `ecosystem` value: `npm` and `PyPI`.
- Vectorizes `package_name` into a deterministic numpy embedding (sha256-based
  n-gram hashing) and writes vectors to `.npy` files.
- Saves ID->index maps as JSON so each stored vector row index corresponds to
  the CSV `id` value (the CSV `id` field is used verbatim as the key).

This implementation uses only the Python stdlib + numpy.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np


# New: hard-coded configuration (do not use CLI args)
INPUT_CSV = "../utils/data/vulnerabilities_npm_pypi_lean.csv"
OUT_DIR = "data/vector_store"
DIM = 128
TOP_K = 5


def read_csv_rows(csv_path: Path) -> List[Dict[str, str]]:
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        return [row for row in reader]


def write_csv_rows(csv_path: Path, rows: List[Dict[str, str]]) -> None:
    if not rows:
        # still write header-less empty file
        with csv_path.open("w", encoding="utf-8", newline="") as fh:
            fh.write("")
        return

    fieldnames = list(rows[0].keys())
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def char_ngram_hash_vector(text: str, dim: int = 128, ngram_sizes: Iterable[int] = (2, 3)) -> np.ndarray:
    """
    Deterministic embedding based on hashed character n-grams.

    - For each n-gram size, hash the n-gram with sha256, take 8 bytes,
      convert to integer, map to an index in [0, dim), and increment that bin.
    - Return an L2-normalized float32 vector.
    """
    vec = np.zeros(dim, dtype=np.float32)
    s = text or ""
    # normalize the input a bit: lower-case and strip
    s = s.strip().lower()

    for n in ngram_sizes:
        if n <= 0:
            continue
        if len(s) < n:
            # hash the whole token if shorter than n
            grams = [s]
        else:
            grams = [s[i : i + n] for i in range(len(s) - n + 1)]

        for g in grams:
            h = hashlib.sha256(g.encode("utf-8")).digest()
            # use first 8 bytes as little-endian integer
            idx = int.from_bytes(h[:8], "little") % dim
            vec[idx] += 1.0

    # L2 normalize (avoid division by zero)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


def batch_embed_cohere(texts: List[str], batch_size: int = 96, model: str = "embed-v4.0") -> List[np.ndarray]:
    """
    Batch embed texts with Cohere if COHERE_API_KEY is set.
    - Reads COHERE_API_KEY from the environment (do NOT hardcode keys).
    - Returns a list of numpy.float32 1-D arrays.
    - Raises RuntimeError if key missing or cohere import fails.
    """
    api_key = os.environ.get("COHERE_API_KEY")
    if not api_key:
        raise RuntimeError("COHERE_API_KEY not set")

    try:
        import cohere  # type: ignore
    except Exception as e:
        raise RuntimeError(f"cohere package not available: {e}")

    client = cohere.Client(api_key)
    all_embeddings: List[np.ndarray] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        # call Cohere embed — adapt to different response shapes safely
        resp = client.embed(texts=batch, model=model, input_type="search_document")
        embeds = getattr(resp, "embeddings", None)
        if embeds is None:
            raise RuntimeError("Cohere response missing embeddings")

        for e in embeds:
            # handle both new-style objects with .float and plain list cases
            if hasattr(e, "float"):
                arr = np.array(e.float, dtype=np.float32)
            else:
                arr = np.array(e, dtype=np.float32)
            all_embeddings.append(arr)
    return all_embeddings


def build_vectors_for_rows(rows: List[Dict[str, str]], dim: int = 128) -> Tuple[np.ndarray, Dict[str, int]]:
    """Return (vectors, id_to_index) for provided rows. Uses `id` column as key.

    Attempt to use Cohere embeddings when COHERE_API_KEY is set; otherwise
    fall back to the existing deterministic char n-gram hashing.
    """
    texts = [r.get("package_name", "") for r in rows]
    embeddings: List[np.ndarray] | None = None

    # Try Cohere if key present
    if os.environ.get("COHERE_API_KEY"):
        try:
            embeddings = batch_embed_cohere(texts, batch_size=96, model="embed-v4.0")
            print(f"Computed {len(embeddings)} embeddings with Cohere")
        except Exception as e:
            # on any failure, fall back to local hashing
            print(f"Cohere embedding failed, falling back to local hashing: {e}")
            embeddings = None

    if embeddings is None:
        # original local hashing path
        vectors = np.zeros((len(rows), dim), dtype=np.float32)
        id_to_index: Dict[str, int] = {}
        for i, row in enumerate(rows):
            pkg = row.get("package_name", "")
            rid = row.get("id") or str(i)
            vec = char_ngram_hash_vector(pkg, dim=dim)
            vectors[i] = vec
            id_to_index[rid] = i
        return vectors, id_to_index

    # Use Cohere embeddings — allow embedding dimension determined by Cohere
    emb_dim = int(embeddings[0].shape[0]) if embeddings else dim
    vectors = np.zeros((len(embeddings), emb_dim), dtype=np.float32)
    id_to_index: Dict[str, int] = {}
    for i, (row, emb) in enumerate(zip(rows, embeddings)):
        arr = np.asarray(emb, dtype=np.float32).reshape(-1)
        if arr.shape[0] != emb_dim:
            # defensive: truncate or pad with zeros
            if arr.shape[0] > emb_dim:
                arr = arr[:emb_dim]
            else:
                pad = np.zeros((emb_dim - arr.shape[0],), dtype=np.float32)
                arr = np.concatenate([arr, pad])
        vectors[i] = arr
        rid = row.get("id") or str(i)
        id_to_index[rid] = i

    # keep an in-memory simple vector_database as the prompt requested (runtime only)
    global vector_database  # simple dict mapping index -> np.array
    vector_database = {i: vectors[i].copy() for i in range(vectors.shape[0])}

    return vectors, id_to_index


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def cosine_search(query_vec: np.ndarray, vectors: np.ndarray, top_k: int = 5) -> List[Tuple[int, float]]:
    """Return list of (index, score) sorted by descending cosine similarity."""
    # assume vectors are L2-normalized
    # if not normalized, we can compute dot/(norms)
    if vectors.size == 0:
        return []
    # ensure query normalized
    q = query_vec.astype(np.float32)
    q_norm = np.linalg.norm(q)
    if q_norm > 0:
        q = q / q_norm

    scores = vectors.dot(q)
    # argsort descending
    idx = np.argsort(-scores)[:top_k]
    return [(int(i), float(scores[i])) for i in idx]


def main(argv=None):
    # Use hard-coded configuration instead of CLI args
    input_csv = Path(INPUT_CSV)
    out_dir = Path(OUT_DIR)
    ensure_dir(out_dir)

    if not input_csv.exists():
        raise SystemExit(f"Input CSV not found: {input_csv}")

    print(f"Reading {input_csv}...")
    rows = read_csv_rows(input_csv)
    print(f"Total rows: {len(rows)}")

    npm_rows = [r for r in rows if (r.get("ecosystem") or "").strip().lower() == "npm"]
    pypi_rows = [r for r in rows if (r.get("ecosystem") or "").strip().lower() == "pypi"]

    print(f"Found npm: {len(npm_rows)}, PyPI: {len(pypi_rows)}")

    # write split CSVs next to input CSV (same folder)
    base_folder = input_csv.parent
    npm_csv = base_folder / "vulnerabilities_npm.csv"
    pypi_csv = base_folder / "vulnerabilities_pypi.csv"

    print(f"Writing split CSVs: {npm_csv}, {pypi_csv}")
    write_csv_rows(npm_csv, npm_rows)
    write_csv_rows(pypi_csv, pypi_rows)

    # Build vectors
    print("Building npm vectors...")
    npm_vectors, npm_map = build_vectors_for_rows(npm_rows, dim=DIM)
    print("Building PyPI vectors...")
    pypi_vectors, pypi_map = build_vectors_for_rows(pypi_rows, dim=DIM)

    # Save outputs
    npm_vec_path = out_dir / "npm_vectors.npy"
    pypi_vec_path = out_dir / "pypi_vectors.npy"
    npm_map_path = out_dir / "npm_id_to_index.json"
    pypi_map_path = out_dir / "pypi_id_to_index.json"

    print(f"Saving numpy vectors to {out_dir}...")
    np.save(npm_vec_path, npm_vectors)
    np.save(pypi_vec_path, pypi_vectors)

    with npm_map_path.open("w", encoding="utf-8") as fh:
        json.dump(npm_map, fh, ensure_ascii=False, indent=2)
    with pypi_map_path.open("w", encoding="utf-8") as fh:
        json.dump(pypi_map, fh, ensure_ascii=False, indent=2)

    print("Done. Vector store written.")



if __name__ == "__main__":
    main()
