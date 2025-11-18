from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Callable, List
from urllib.parse import urlsplit, urlunsplit

from git import Repo
from langchain_core.documents import Document
import json


def clone_repo(repo_url: str, base_dir: str | None = None) -> Path:
    """
    Clone a Git repo into base_dir and return the local path.
    """
    if base_dir is None:
        base_dir = tempfile.mkdtemp(prefix="repo_ingest_")

    # Normalize the incoming URL: remove query string and fragment
    # and ensure it ends with ".git" so `git clone` accepts it.
    parsed = urlsplit(repo_url)
    parsed = parsed._replace(query="", fragment="")
    normalized = urlunsplit(parsed)
    if not normalized.endswith(".git"):
        normalized = normalized.rstrip("/") + ".git"

    # Derive repository folder name from the path component (without .git)
    repo_name = Path(parsed.path).stem
    repo_path = Path(base_dir) / repo_name

    Repo.clone_from(normalized, repo_path)
    return repo_path


def repo_to_documents(repo_path: Path) -> List[Document]:
    """
    Walk the repo and convert text-like files to LangChain Documents.
    Includes all files except symlinks and executables.
    """
    docs: List[Document] = []

    for root, dirs, files in os.walk(repo_path):
        # Skip typical junk dirs
        dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "dist", "build", ".venv", "__pycache__"}]

        for fname in files:
            path = Path(root) / fname

            # Skip symlinks
            if path.is_symlink():
                continue

            # Skip executables
            try:
                if os.access(path, os.X_OK):
                    continue
            except Exception:
                # conservative: skip on access check failure
                continue

            # No binary heuristic — include all remaining files
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            rel_path = path.relative_to(repo_path)

            docs.append(
                Document(
                    page_content=text,
                    metadata={
                        "path": str(rel_path),
                        "repo_root": str(repo_path),
                    },
                )
            )
    return docs


def ingest_repository(
    repo_url: str,
    index_fn: Callable[[List[Document]], None],
    base_dir: str | None = None,
) -> List[Document]:
    """
    High-level function you expose to the rest of the system.

    - `repo_url`: GitHub/GitLab URL
    - `index_fn`: callback that takes Documents and indexes them
                  (e.g. calls your embedding worker + vector DB)
    - returns: the list of created Documents (optional, for debugging)
    """
    repo_path = clone_repo(repo_url, base_dir=base_dir)
    docs = repo_to_documents(repo_path)
    index_fn(docs)
    return docs


# Example usage:
if __name__ == "__main__":
    def chunk_text(text: str, max_chars: int = 1000, overlap: int = 200) -> List[str]:
        """
        Split `text` into chunks of up to `max_chars`, with `overlap` characters overlap.
        This is a simple, safe character-based splitter for demonstration.
        """
        if max_chars <= 0:
            raise ValueError("max_chars must be > 0")

        if overlap < 0:
            overlap = 0

        chunks: List[str] = []
        start = 0
        length = len(text)
        while start < length:
            end = start + max_chars
            chunk = text[start:end]
            chunks.append(chunk)
            if end >= length:
                break
            start = end - overlap

        return chunks


    def file_index_fn(docs: List[Document], output_dir: str | Path = "./data/chunks") -> None:
        """
        Index function that writes document chunks to disk as JSON files.

        - `output_dir`: directory where chunk files are written. Each chunk is a
          separate JSON file named `<safe-path>_chunk<index>.json`.
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        total_chunks = 0
        for doc in docs:
            text = doc.page_content or ""
            rel_path = doc.metadata.get("path", "unknown")
            repo_root = doc.metadata.get("repo_root")

            safe_name = rel_path.replace("/", "_").replace("\\", "_")
            if not safe_name:
                safe_name = "unnamed"

            chunks = chunk_text(text, max_chars=1000, overlap=200)

            for i, chunk in enumerate(chunks):
                filename = f"{safe_name}_chunk{i+1}.json"
                target = out / filename
                payload = {
                    "repo_root": repo_root,
                    "path": rel_path,
                    "chunk_index": i + 1,
                    "total_chunks_for_doc": len(chunks),
                    "text": chunk,
                    "original_length": len(text),
                }

                try:
                    with target.open("w", encoding="utf-8") as fh:
                        json.dump(payload, fh, ensure_ascii=False, indent=2)
                    total_chunks += 1
                except Exception:
                    # Best-effort: skip files we can't write
                    continue

        print(f"Wrote {total_chunks} chunk files to {str(out)}")


    test_repo_url = "https://github.com/ai-yann/vilnius-workshop.git"
    # Use the file-based indexer and write chunks to ./data/chunks
    ingest_repository(test_repo_url, lambda docs: file_index_fn(docs, output_dir="./data/chunks"))
