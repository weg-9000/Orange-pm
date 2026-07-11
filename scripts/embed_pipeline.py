#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Chunks Markdown files, generates embeddings, and loads them into Neo4j. (Chonkie-based)

Usage:
    python embed_pipeline.py --product <product_name> [--dry-run]
    python embed_pipeline.py --product <product_name> --model local
    python embed_pipeline.py --product <product_name> --force
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

# ── Chonkie import ────────────────────────────────────────────────────────────
try:
    import chonkie as _chonkie_pkg
    from chonkie import RecursiveChunker, EmbeddingsRefinery
    CHONKIE_VERSION = getattr(_chonkie_pkg, "__version__", "unknown")
except ImportError:
    print("[chonkie not installed]")
    print('pip install "chonkie[tiktoken,voyageai,st]"')
    sys.exit(1)


# ── Constants ────────────────────────────────────────────────────────────────
PARQUET_FILENAME = "chunks.parquet"
EMBEDDING_DIM = 768
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
VOYAGE_MODEL = "voyage-3"
LOCAL_MODEL = "paraphrase-multilingual-mpnet-base-v2"
BATCH_SIZE = 64

_DOC_ID_RE = re.compile(r"[A-Z]\d+-[A-Z](?:-\d+)?")


# ── Argument parsing ─────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Markdown chunking + embedding → Neo4j loading pipeline (Chonkie-based)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python embed_pipeline.py --product my-product
  python embed_pipeline.py --product my-product --dry-run
  python embed_pipeline.py --product my-product --model local
  python embed_pipeline.py --product my-product --force \\
      --neo4j-uri bolt://db.internal:7687 \\
      --neo4j-user admin
        """,
    )
    p.add_argument("--product", required=True,
                   help="Determines the PROJECTS/{product}/drafts/ path")
    p.add_argument("--neo4j-uri", default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
                   help="Neo4j Bolt URI (env NEO4J_URI / default bolt://localhost:7687). "
                        "Cloud/Aura uses the neo4j+s://<host> format.")
    p.add_argument("--neo4j-user", default=os.environ.get("NEO4J_USER", "neo4j"),
                   help="Neo4j username (env NEO4J_USER / default neo4j)")
    p.add_argument("--neo4j-password", default=None,
                   help="Neo4j password. NEO4J_PASSWORD env var takes precedence")
    p.add_argument("--model", choices=["anthropic", "local"], default=None,
                   help="[legacy compat] local→default local model / anthropic→voyage-3. "
                        "If omitted, uses env ORANGE_EMBED_MODEL or the default (bge-m3, local). "
                        "Model and dimension are resolved from the single source of truth, "
                        "_embed_config.")
    p.add_argument("--force", action="store_true",
                   help="Ignore the checkpoint (chunks.parquet) and reprocess everything")
    p.add_argument("--dry-run", action="store_true",
                   help="Only print chunking results; skip embedding/loading")
    p.add_argument("--prune", action="store_true",
                   help="Remove chunks for files that no longer exist from parquet/Neo4j "
                        "(deletion sync)")
    return p


# ── PREFIX detection ──────────────────────────────────────────────────────────

_ACTIVE_PREFIX_RE = re.compile(r"^ACTIVE_PREFIX:\s*([A-Za-z0-9_-]+)\s*$", re.MULTILINE)
_PREFIX_RE = re.compile(r"^PREFIX:\s*([A-Za-z0-9_-]+)\s*$", re.MULTILINE)
_PREFIXES_ITEM_RE = re.compile(r"^\s*-\s*id:\s*([A-Za-z0-9_-]+)\s*$", re.MULTILINE)


def _layer_config_text() -> str | None:
    layer_config = Path("CONTEXT") / "layer-config.md"
    if not layer_config.exists():
        return None
    return layer_config.read_text(encoding="utf-8")


def detect_prefix() -> str | None:
    """Extract the active PREFIX (e.g. G2) from CONTEXT/layer-config.md.

    Priority: ``ACTIVE_PREFIX:`` -> ``PREFIX:`` -> (legacy) doc_id pattern guess.
    """
    content = _layer_config_text()
    if content is None:
        return None
    m = _ACTIVE_PREFIX_RE.search(content) or _PREFIX_RE.search(content)
    if m:
        return m.group(1)
    m = _DOC_ID_RE.search(content)
    if m:
        return m.group(0).split("-")[0]
    return None


def detect_prefixes() -> list[str]:
    """Return the full list of declared PREFIXes (multi-PREFIX). Falls back to the single active one if none declared."""
    content = _layer_config_text()
    if content is None:
        return []
    ids = _PREFIXES_ITEM_RE.findall(content)
    if ids:
        return ids
    one = detect_prefix()
    return [one] if one else []


# ── File collection ─────────────────────────────────────────────────────────

def collect_files(product: str) -> list[Path]:
    sources: list[Path] = []

    drafts_dir = Path("PROJECTS") / product / "drafts"
    if drafts_dir.exists():
        sources.extend(sorted(drafts_dir.glob("*.md")))
    else:
        print(f"[WARN] drafts directory not found: {drafts_dir}", file=sys.stderr)

    ref_dir = Path("CONTEXT") / "reference-docs"
    if ref_dir.exists():
        sources.extend(sorted(ref_dir.rglob("*.md")))
    else:
        print(f"[WARN] reference-docs directory not found: {ref_dir}", file=sys.stderr)

    return sources


# ── Metadata helpers ─────────────────────────────────────────────────────────

def _extract_doc_id(file_path: Path) -> str:
    m = _DOC_ID_RE.search(file_path.stem)
    return m.group(0) if m else file_path.stem


def _extract_layer(file_path: Path, prefix: str | None) -> str:
    pfx = prefix or "G"
    parts = file_path.parts
    if "reference-docs" in parts:
        idx = list(parts).index("reference-docs")
        rest = parts[idx + 1:]
        # New nested layout: reference-docs/{PREFIX}/{A,B,C}/... — use the PREFIX from the path
        if len(rest) >= 2 and rest[1].upper() in ("A", "B", "C"):
            return f"{rest[0]}-{rest[1].upper()}"
        # Legacy flat layout: reference-docs/{A,B,C}/... — apply the active PREFIX
        if len(rest) >= 1 and rest[0].upper() in ("A", "B", "C"):
            return f"{pfx}-{rest[0].upper()}"
    if "drafts" in parts:
        return f"{pfx}-D"
    return pfx


def _extract_section_title(text: str, file_path: Path) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## ") or s.startswith("### "):
            return s.lstrip("#").strip()
    return file_path.stem


def _derive_prefix(file_path: Path, active: str | None) -> str:
    """Extract PREFIX from the path (nested reference-docs/{PREFIX}/...); falls back to the active PREFIX."""
    parts = file_path.parts
    if "reference-docs" in parts:
        idx = list(parts).index("reference-docs")
        rest = parts[idx + 1:]
        if len(rest) >= 2 and rest[1].upper() in ("A", "B", "C"):
            return rest[0]
    return active or ""


def _derive_service(file_path: Path) -> str:
    """Extract the C service: reference-docs/{PREFIX}/C/{service}/... → service, else ''."""
    parts = file_path.parts
    if "reference-docs" in parts:
        idx = list(parts).index("reference-docs")
        rest = parts[idx + 1:]
        # {PREFIX}/C/{service}/...
        if len(rest) >= 3 and rest[1].upper() == "C":
            return rest[2]
    return ""


def _derive_doc_type(file_path: Path) -> str:
    """Extract doc_type from the d1-d5 naming convention or the .complete/.draft suffix."""
    stem = file_path.stem
    m = re.match(r"(d[1-5])\b", stem)
    if m:
        return m.group(1)
    if stem.endswith(".complete"):
        return "complete"
    if stem.endswith(".draft"):
        return "draft"
    return ""


def _to_list(vec: Any) -> list[float]:
    if hasattr(vec, "tolist"):
        return vec.tolist()
    return list(vec)


def _make_chunk_id(file_path: Path, index: int, text: str) -> str:
    return hashlib.sha256(
        f"{file_path}::{index}::{text[:200]}".encode()
    ).hexdigest()[:16]


# ── Checkpoint ───────────────────────────────────────────────────────────────

def _parquet_path(product: str) -> Path:
    return Path("PROJECTS") / product / "graph" / PARQUET_FILENAME


def load_processed_files(product: str) -> dict[str, float]:
    """Return a {source_file: mtime at processing time} mapping from chunks.parquet.

    If the source_mtime column is absent (an older checkpoint), treat it as
    0.0 — this conservatively re-embeds on any change detection.
    """
    cp = _parquet_path(product)
    if not cp.exists():
        return {}
    try:
        import pandas as pd
        df = pd.read_parquet(cp)
        if "source_file" not in df.columns:
            return {}
        if "source_mtime" in df.columns:
            return df.groupby("source_file")["source_mtime"].max().to_dict()
        return {sf: 0.0 for sf in df["source_file"].unique()}
    except ImportError:
        print("[ERROR] pandas/pyarrow package not installed. Run pip install pandas pyarrow.",
              file=sys.stderr)
        sys.exit(1)


def _needs_reembed(f: Path, processed: dict[str, float]) -> bool:
    key = str(f)
    if key not in processed:
        return True
    try:
        return f.stat().st_mtime > processed[key] + 1e-6
    except OSError:
        return True


def load_all_records(product: str) -> list[dict]:
    cp = _parquet_path(product)
    if not cp.exists():
        return []
    try:
        import pandas as pd
        return pd.read_parquet(cp).to_dict("records")
    except ImportError:
        print("[ERROR] pandas/pyarrow package not installed. Run pip install pandas pyarrow.",
              file=sys.stderr)
        sys.exit(1)


def save_checkpoint(product: str, records: list[dict]) -> None:
    cp = _parquet_path(product)
    cp.parent.mkdir(parents=True, exist_ok=True)
    try:
        import pandas as pd
        pd.DataFrame(records).to_parquet(cp, index=False)
    except ImportError:
        print("[ERROR] pandas/pyarrow package not installed. Run pip install pandas pyarrow.",
              file=sys.stderr)
        sys.exit(1)
    print(f"[INFO] checkpoint saved: {cp} ({len(records)} records)")


# ── Embedding model factory ──────────────────────────────────────────────────

def _build_from_spec(spec: dict):
    """spec({provider,name,dim}) -> chonkie embedding instance."""
    if spec["provider"] == "voyage":
        api_key = os.environ.get("VOYAGE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("[No Voyage API key (VOYAGE_API_KEY) — falling back to the local model]")
            import _embed_config as _ec
            return _build_from_spec(_ec.EMBED_MODELS[_ec.DEFAULT_MODEL] | {"key": _ec.DEFAULT_MODEL})
        try:
            from chonkie.embeddings import VoyageAIEmbeddings
            return VoyageAIEmbeddings(model=spec["name"], api_key=api_key)
        except ImportError:
            print("[ERROR] chonkie voyageai dependency not installed.", file=sys.stderr)
            print('pip install "chonkie[voyageai]"', file=sys.stderr)
            sys.exit(1)
    try:
        from chonkie.embeddings import SentenceTransformerEmbeddings
        # Local run — model weights auto-download on first call (no key needed, CPU/GPU auto-detected).
        return SentenceTransformerEmbeddings(model=spec["name"])
    except ImportError:
        print("[sentence-transformers not installed]")
        print('pip install "chonkie[st]"')
        sys.exit(1)


def build_embeddings_model(model_type: str | None = None):
    """[Backward-compat + shared] Resolves env ORANGE_EMBED_MODEL / --model and returns an embedding instance.

    context_search also calls this function, so the loading and search models always match.
    """
    import _embed_config as _ec
    return _build_from_spec(_ec.resolve_model(model_type))


# ── Neo4j ────────────────────────────────────────────────────────────────────

def get_driver(uri: str, user: str, password: str):
    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("[ERROR] neo4j package not installed. Run pip install neo4j.",
              file=sys.stderr)
        sys.exit(1)
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        return driver
    except Exception as e:
        print(f"[ERROR] Neo4j connection failed: {e}", file=sys.stderr)
        print(f"        URI: {uri}, user: {user}", file=sys.stderr)
        sys.exit(1)


def ensure_vector_index(session, dims: int = EMBEDDING_DIM) -> None:
    # The index dimension must match the chosen embedding model's dimension (_embed_config).
    session.run(
        """
        CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS
        FOR (c:Chunk) ON (c.embedding)
        OPTIONS {indexConfig: {
            `vector.dimensions`: $dims,
            `vector.similarity_function`: 'cosine'
        }}
        """,
        dims=dims,
    )


def compute_removed(known_files: set[str], current_files: set[str]) -> list[str]:
    """List of files present in the previous load (parquet) but absent from the current collection (= deleted)."""
    return sorted(known_files - current_files)


def delete_chunks_for_files(session, source_files: list[str]) -> int:
    """Remove :Chunk nodes for the given source_files from Neo4j and return the delete count.

    Modification sync: removes stale chunks for re-embedded files (leftover
    nodes whose chunk_id changed due to text changes) and chunks for deleted
    files, keeping Neo4j consistent with the current document state.
    """
    if not source_files:
        return 0
    res = session.run(
        "MATCH (c:Chunk) WHERE c.source_file IN $files DETACH DELETE c",
        files=source_files,
    )
    return res.consume().counters.nodes_deleted


def merge_chunks(session, records: list[dict]) -> int:
    count = 0
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i : i + BATCH_SIZE]
        for rec in batch:
            session.run(
                """
                MERGE (c:Chunk {chunk_id: $chunk_id})
                SET c.source_file   = $source_file,
                    c.doc_id        = $doc_id,
                    c.section_title = $section_title,
                    c.chunk_index   = $chunk_index,
                    c.layer         = $layer,
                    c.prefix        = $prefix,
                    c.service       = $service,
                    c.doc_type      = $doc_type,
                    c.char_count    = $char_count,
                    c.token_count   = $token_count,
                    c.text          = $text,
                    c.embedding     = $embedding
                """,
                chunk_id=rec["chunk_id"],
                source_file=rec["source_file"],
                doc_id=rec["doc_id"],
                section_title=rec["section_title"],
                chunk_index=rec["chunk_index"],
                layer=rec["layer"],
                prefix=rec.get("prefix", ""),
                service=rec.get("service", ""),
                doc_type=rec.get("doc_type", ""),
                char_count=rec["char_count"],
                token_count=rec["token_count"],
                text=rec["text"],
                embedding=rec["embedding"],
            )
            count += 1
    return count


def link_chunks_to_nodes(session) -> None:
    """Link [:HAS_CHUNK] relationships to Policy/Reference nodes by doc_id."""
    session.run(
        """
        MATCH (c:Chunk)
        WHERE c.doc_id IS NOT NULL
        OPTIONAL MATCH (p:Policy {doc_id: c.doc_id})
        OPTIONAL MATCH (r:Reference {doc_id: c.doc_id})
        WITH c, coalesce(p, r) AS parent
        WHERE parent IS NOT NULL
        MERGE (parent)-[:HAS_CHUNK]->(c)
        """
    )


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    args = build_parser().parse_args()

    password = os.environ.get("NEO4J_PASSWORD") or args.neo4j_password
    if not password and not args.dry_run:
        print("[ERROR] No Neo4j password.", file=sys.stderr)
        print("        Use the NEO4J_PASSWORD env var or the --neo4j-password argument.",
              file=sys.stderr)
        sys.exit(1)

    start_time = time.time()
    prefix = detect_prefix()

    # 1. collect files
    files = collect_files(args.product)
    if not files:
        print("[ERROR] No markdown files to process.", file=sys.stderr)
        sys.exit(1)
    print(f"[INFO] files collected: {len(files)}")

    # 2. check checkpoint — skip based on source_file
    if args.force:
        processed: dict[str, float] = {}
        cached_records: list[dict] = []
    else:
        processed = load_processed_files(args.product)
        cached_records = load_all_records(args.product)

    # Re-embed only new + changed (mtime up) files. Remove stale chunks of changed files from the cache.
    new_files = [f for f in files if _needs_reembed(f, processed)]
    reembed = {str(f) for f in new_files}
    if reembed:
        cached_records = [r for r in cached_records if r.get("source_file") not in reembed]
    skip_count = len(files) - len(new_files)
    print(f"[INFO] to process: {len(new_files)} / skipped: {skip_count}")

    # Deletion sync (--prune): files present in the previous load but absent now = deleted -> remove from parquet/Neo4j
    current_files = {str(f) for f in files}
    known_files = set(load_processed_files(args.product).keys())
    removed_files = compute_removed(known_files, current_files) if args.prune else []
    if removed_files:
        cached_records = [r for r in cached_records if r.get("source_file") not in set(removed_files)]
        print(f"[INFO] deletion sync targets (--prune): {len(removed_files)} files")

    # 3. chunking — RecursiveChunker(recipe="markdown")
    chunker = RecursiveChunker(
        tokenizer="tiktoken",
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        recipe="markdown",
    )

    file_chunk_map: list[tuple[Path, list]] = []
    for f in new_files:
        raw = chunker(f.read_text(encoding="utf-8"))
        file_chunk_map.append((f, raw))
        print(f"       {f.name}: {len(raw)} chunks")

    total_new = sum(len(c) for _, c in file_chunk_map)
    total_chunks = len(cached_records) + total_new
    print(f"[INFO] total chunks: {total_chunks} (new: {total_new})")

    if args.dry_run:
        print("\n[DRY-RUN] Exiting without embedding/loading.")
        if removed_files:
            print(f"[DRY-RUN] deletion sync planned (--prune): {len(removed_files)} files")
        layer_counts: dict[str, int] = {}
        for f, raw in file_chunk_map:
            lyr = _extract_layer(f, prefix)
            layer_counts[lyr] = layer_counts.get(lyr, 0) + len(raw)
        for lyr, cnt in layer_counts.items():
            print(f"[DRY-RUN]   {lyr}: {cnt} chunks")
        return

    # 4. embedding — EmbeddingsRefinery. Model/dimension resolved from the single source of truth, _embed_config.
    import _embed_config as _ec
    spec = _ec.resolve_model(args.model)
    embed_dim = spec["dim"]
    model_name = spec["name"]
    all_raw_chunks = [c for _, chunks in file_chunk_map for c in chunks]

    if all_raw_chunks:
        print(f"[INFO] generating embeddings (model={spec['key']} dim={embed_dim}, {len(all_raw_chunks)} items)...")
        embeddings_model = _build_from_spec(spec)
        refinery = EmbeddingsRefinery(embeddings=embeddings_model)
        embedded = refinery(all_raw_chunks)
        model_name = getattr(embeddings_model, "model", model_name)
    else:
        embedded = []

    # 5. attach metadata -> build records
    new_records: list[dict] = []
    emb_idx = 0
    for f, raw_chunks in file_chunk_map:
        doc_id = _extract_doc_id(f)
        layer = _extract_layer(f, prefix)
        file_prefix = _derive_prefix(f, prefix)
        service = _derive_service(f)
        doc_type = _derive_doc_type(f)
        try:
            source_mtime = f.stat().st_mtime
        except OSError:
            source_mtime = 0.0
        for i in range(len(raw_chunks)):
            ec = embedded[emb_idx]
            emb_idx += 1
            new_records.append({
                "chunk_id": _make_chunk_id(f, i, ec.text),
                "source_file": str(f),
                "source_mtime": source_mtime,
                "doc_id": doc_id,
                "section_title": _extract_section_title(ec.text, f),
                "chunk_index": i,
                "layer": layer,
                "prefix": file_prefix,
                "service": service,
                "doc_type": doc_type,
                "phase": "",
                "node_type": "Chunk",
                "char_count": len(ec.text),
                "token_count": getattr(ec, "token_count", 0),
                "text": ec.text,
                "embedding": _to_list(ec.embedding),
            })

    # 6. save checkpoint
    final_records = cached_records + new_records
    save_checkpoint(args.product, final_records)

    # 7. load into Neo4j
    driver = get_driver(args.neo4j_uri, args.neo4j_user, password)
    neo4j_count = 0
    try:
        with driver.session() as session:
            print(f"[INFO] checking/creating vector index (dim={embed_dim})...")
            ensure_vector_index(session, embed_dim)
            # Modification sync: remove stale chunks of re-embedded files + chunks of deleted files first (avoids ghost chunks).
            stale_files = sorted(set(reembed) | set(removed_files))
            if stale_files:
                deleted = delete_chunks_for_files(session, stale_files)
                print(f"[INFO] removed stale/deleted chunks: {deleted} (across {len(stale_files)} files)")
            print("[INFO] starting :Chunk node MERGE...")
            neo4j_count = merge_chunks(session, final_records)
            print("[INFO] starting [:HAS_CHUNK] relationship linking...")
            link_chunks_to_nodes(session)
    finally:
        driver.close()

    elapsed = time.time() - start_time
    print(f"\n[DONE] elapsed time: {elapsed:.1f}s")
    print(f"[DONE] files processed: {len(new_files)} (skipped: {skip_count})")
    print(f"[DONE] total chunks: {total_chunks}")
    print(f"[DONE] embedding model: {model_name}")
    print(f"[DONE] Neo4j (:Chunk) nodes: {neo4j_count}")
    print(f"[DONE] chunking library: chonkie {CHONKIE_VERSION}")


if __name__ == "__main__":
    main()
