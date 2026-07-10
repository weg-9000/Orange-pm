#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""마크다운 파일을 청킹하고 임베딩을 생성해 Neo4j에 적재한다. (Chonkie 기반)

사용:
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

# ── Chonkie 임포트 ────────────────────────────────────────────────────────────
try:
    import chonkie as _chonkie_pkg
    from chonkie import RecursiveChunker, EmbeddingsRefinery
    CHONKIE_VERSION = getattr(_chonkie_pkg, "__version__", "unknown")
except ImportError:
    print("[chonkie 미설치]")
    print('pip install "chonkie[tiktoken,voyageai,st]"')
    sys.exit(1)


# ── 상수 ─────────────────────────────────────────────────────────────────────
PARQUET_FILENAME = "chunks.parquet"
EMBEDDING_DIM = 768
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
VOYAGE_MODEL = "voyage-3"
LOCAL_MODEL = "paraphrase-multilingual-mpnet-base-v2"
BATCH_SIZE = 64

_DOC_ID_RE = re.compile(r"[A-Z]\d+-[A-Z](?:-\d+)?")


# ── 인수 파싱 ────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="마크다운 청킹 + 임베딩 → Neo4j 적재 파이프라인 (Chonkie 기반)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python embed_pipeline.py --product my-product
  python embed_pipeline.py --product my-product --dry-run
  python embed_pipeline.py --product my-product --model local
  python embed_pipeline.py --product my-product --force \\
      --neo4j-uri bolt://db.internal:7687 \\
      --neo4j-user admin
        """,
    )
    p.add_argument("--product", required=True,
                   help="PROJECTS/{product}/drafts/ 경로 결정")
    p.add_argument("--neo4j-uri", default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
                   help="Neo4j Bolt URI (env NEO4J_URI / 기본 bolt://localhost:7687). "
                        "클라우드/Aura 는 neo4j+s://<host> 형식.")
    p.add_argument("--neo4j-user", default=os.environ.get("NEO4J_USER", "neo4j"),
                   help="Neo4j 사용자명 (env NEO4J_USER / 기본 neo4j)")
    p.add_argument("--neo4j-password", default=None,
                   help="Neo4j 비밀번호. NEO4J_PASSWORD 환경변수 우선 적용")
    p.add_argument("--model", choices=["anthropic", "local"], default=None,
                   help="[하위호환] local→기본 로컬모델 / anthropic→voyage-3. "
                        "미지정 시 env ORANGE_EMBED_MODEL 또는 기본(bge-m3, 로컬). "
                        "모델·차원은 _embed_config 단일 출처에서 결정된다.")
    p.add_argument("--force", action="store_true",
                   help="체크포인트(chunks.parquet) 무시하고 전체 재처리")
    p.add_argument("--dry-run", action="store_true",
                   help="청킹 결과만 출력하고 임베딩·적재는 수행하지 않음")
    p.add_argument("--prune", action="store_true",
                   help="더 이상 존재하지 않는 파일의 청크를 parquet·Neo4j 에서 제거(삭제 동기화)")
    return p


# ── PREFIX 감지 ───────────────────────────────────────────────────────────────

_ACTIVE_PREFIX_RE = re.compile(r"^ACTIVE_PREFIX:\s*([A-Za-z0-9_-]+)\s*$", re.MULTILINE)
_PREFIX_RE = re.compile(r"^PREFIX:\s*([A-Za-z0-9_-]+)\s*$", re.MULTILINE)
_PREFIXES_ITEM_RE = re.compile(r"^\s*-\s*id:\s*([A-Za-z0-9_-]+)\s*$", re.MULTILINE)


def _layer_config_text() -> str | None:
    layer_config = Path("CONTEXT") / "layer-config.md"
    if not layer_config.exists():
        return None
    return layer_config.read_text(encoding="utf-8")


def detect_prefix() -> str | None:
    """CONTEXT/layer-config.md에서 활성 PREFIX(예: G2)를 추출한다.

    우선순위: ``ACTIVE_PREFIX:`` → ``PREFIX:`` → (레거시) doc_id 패턴 추정.
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
    """선언된 전체 PREFIX 목록을 반환한다 (멀티-PREFIX). 없으면 활성 1개로 폴백."""
    content = _layer_config_text()
    if content is None:
        return []
    ids = _PREFIXES_ITEM_RE.findall(content)
    if ids:
        return ids
    one = detect_prefix()
    return [one] if one else []


# ── 파일 수집 ────────────────────────────────────────────────────────────────

def collect_files(product: str) -> list[Path]:
    sources: list[Path] = []

    drafts_dir = Path("PROJECTS") / product / "drafts"
    if drafts_dir.exists():
        sources.extend(sorted(drafts_dir.glob("*.md")))
    else:
        print(f"[WARN] drafts 디렉터리 없음: {drafts_dir}", file=sys.stderr)

    ref_dir = Path("CONTEXT") / "reference-docs"
    if ref_dir.exists():
        sources.extend(sorted(ref_dir.rglob("*.md")))
    else:
        print(f"[WARN] reference-docs 디렉터리 없음: {ref_dir}", file=sys.stderr)

    return sources


# ── 메타데이터 헬퍼 ───────────────────────────────────────────────────────────

def _extract_doc_id(file_path: Path) -> str:
    m = _DOC_ID_RE.search(file_path.stem)
    return m.group(0) if m else file_path.stem


def _extract_layer(file_path: Path, prefix: str | None) -> str:
    pfx = prefix or "G"
    parts = file_path.parts
    if "reference-docs" in parts:
        idx = list(parts).index("reference-docs")
        rest = parts[idx + 1:]
        # 신규 중첩: reference-docs/{PREFIX}/{A,B,C}/... — 경로의 PREFIX 를 우선 사용
        if len(rest) >= 2 and rest[1].upper() in ("A", "B", "C"):
            return f"{rest[0]}-{rest[1].upper()}"
        # 레거시 평면: reference-docs/{A,B,C}/... — 활성 PREFIX 적용
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
    """경로에서 PREFIX 추출(중첩 reference-docs/{PREFIX}/...), 없으면 활성 PREFIX."""
    parts = file_path.parts
    if "reference-docs" in parts:
        idx = list(parts).index("reference-docs")
        rest = parts[idx + 1:]
        if len(rest) >= 2 and rest[1].upper() in ("A", "B", "C"):
            return rest[0]
    return active or ""


def _derive_service(file_path: Path) -> str:
    """C 서비스 추출: reference-docs/{PREFIX}/C/{service}/... → service, 그 외 ''."""
    parts = file_path.parts
    if "reference-docs" in parts:
        idx = list(parts).index("reference-docs")
        rest = parts[idx + 1:]
        # {PREFIX}/C/{service}/...
        if len(rest) >= 3 and rest[1].upper() == "C":
            return rest[2]
    return ""


def _derive_doc_type(file_path: Path) -> str:
    """완결판 명명 규약 d1~d5 또는 .complete/.draft 표기에서 doc_type 추출."""
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


# ── 체크포인트 ────────────────────────────────────────────────────────────────

def _parquet_path(product: str) -> Path:
    return Path("PROJECTS") / product / "graph" / PARQUET_FILENAME


def load_processed_files(product: str) -> dict[str, float]:
    """chunks.parquet에서 {source_file: 처리 당시 mtime} 매핑 반환.

    source_mtime 컬럼이 없으면(구버전 체크포인트) 0.0 으로 본다 → 변경 감지 시
    재임베딩되도록 보수적으로 동작한다.
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
        print("[ERROR] pandas/pyarrow 패키지가 없습니다. pip install pandas pyarrow 를 실행하세요.",
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
        print("[ERROR] pandas/pyarrow 패키지가 없습니다. pip install pandas pyarrow 를 실행하세요.",
              file=sys.stderr)
        sys.exit(1)


def save_checkpoint(product: str, records: list[dict]) -> None:
    cp = _parquet_path(product)
    cp.parent.mkdir(parents=True, exist_ok=True)
    try:
        import pandas as pd
        pd.DataFrame(records).to_parquet(cp, index=False)
    except ImportError:
        print("[ERROR] pandas/pyarrow 패키지가 없습니다. pip install pandas pyarrow 를 실행하세요.",
              file=sys.stderr)
        sys.exit(1)
    print(f"[INFO] 체크포인트 저장: {cp} ({len(records)}건)")


# ── 임베딩 모델 팩토리 ────────────────────────────────────────────────────────

def _build_from_spec(spec: dict):
    """spec({provider,name,dim}) → chonkie 임베딩 인스턴스."""
    if spec["provider"] == "voyage":
        api_key = os.environ.get("VOYAGE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("[Voyage API 키 없음(VOYAGE_API_KEY) — 로컬 모델로 전환]")
            import _embed_config as _ec
            return _build_from_spec(_ec.EMBED_MODELS[_ec.DEFAULT_MODEL] | {"key": _ec.DEFAULT_MODEL})
        try:
            from chonkie.embeddings import VoyageAIEmbeddings
            return VoyageAIEmbeddings(model=spec["name"], api_key=api_key)
        except ImportError:
            print("[ERROR] chonkie voyageai 의존성이 없습니다.", file=sys.stderr)
            print('pip install "chonkie[voyageai]"', file=sys.stderr)
            sys.exit(1)
    try:
        from chonkie.embeddings import SentenceTransformerEmbeddings
        # 로컬 실행 — 첫 호출 시 모델 가중치 자동 다운로드(키 불요, CPU/GPU 자동).
        return SentenceTransformerEmbeddings(model=spec["name"])
    except ImportError:
        print("[sentence-transformers 미설치]")
        print('pip install "chonkie[st]"')
        sys.exit(1)


def build_embeddings_model(model_type: str | None = None):
    """[하위호환 + 공용] env ORANGE_EMBED_MODEL / --model 을 해소해 임베딩 인스턴스 반환.

    context_search 도 본 함수를 호출하므로 적재·검색 모델이 항상 일치한다.
    """
    import _embed_config as _ec
    return _build_from_spec(_ec.resolve_model(model_type))


# ── Neo4j ────────────────────────────────────────────────────────────────────

def get_driver(uri: str, user: str, password: str):
    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("[ERROR] neo4j 패키지가 없습니다. pip install neo4j 를 실행하세요.",
              file=sys.stderr)
        sys.exit(1)
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        return driver
    except Exception as e:
        print(f"[ERROR] Neo4j 연결 실패: {e}", file=sys.stderr)
        print(f"        URI: {uri}, 사용자: {user}", file=sys.stderr)
        sys.exit(1)


def ensure_vector_index(session, dims: int = EMBEDDING_DIM) -> None:
    # 인덱스 차원은 선택한 임베딩 모델 차원과 반드시 일치해야 한다(_embed_config).
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
    """이전 적재(parquet)에는 있으나 현재 수집 목록에 없는 파일(=삭제됨) 목록."""
    return sorted(known_files - current_files)


def delete_chunks_for_files(session, source_files: list[str]) -> int:
    """주어진 source_file 들의 :Chunk 노드를 Neo4j 에서 제거하고 삭제 수를 반환.

    수정 동기화: 재임베딩 대상 파일의 옛 청크(텍스트 변경으로 chunk_id 가 바뀐 잔존 노드)와
    삭제된 파일의 청크를 제거해 Neo4j 가 현재 문서 상태와 일치하도록 한다.
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
    """doc_id로 Policy/Reference 노드와 [:HAS_CHUNK] 관계 연결."""
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


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main() -> None:
    args = build_parser().parse_args()

    password = os.environ.get("NEO4J_PASSWORD") or args.neo4j_password
    if not password and not args.dry_run:
        print("[ERROR] Neo4j 비밀번호가 없습니다.", file=sys.stderr)
        print("        NEO4J_PASSWORD 환경변수 또는 --neo4j-password 인수를 사용하세요.",
              file=sys.stderr)
        sys.exit(1)

    start_time = time.time()
    prefix = detect_prefix()

    # 1. 파일 수집
    files = collect_files(args.product)
    if not files:
        print("[ERROR] 처리할 마크다운 파일이 없습니다.", file=sys.stderr)
        sys.exit(1)
    print(f"[INFO] 수집된 파일: {len(files)}개")

    # 2. 체크포인트 확인 — source_file 기준 스킵
    if args.force:
        processed: dict[str, float] = {}
        cached_records: list[dict] = []
    else:
        processed = load_processed_files(args.product)
        cached_records = load_all_records(args.product)

    # 신규 + 변경(mtime↑) 파일만 재임베딩. 변경 파일의 stale 청크는 캐시에서 제거.
    new_files = [f for f in files if _needs_reembed(f, processed)]
    reembed = {str(f) for f in new_files}
    if reembed:
        cached_records = [r for r in cached_records if r.get("source_file") not in reembed]
    skip_count = len(files) - len(new_files)
    print(f"[INFO] 처리 대상: {len(new_files)}개 / 스킵: {skip_count}개")

    # 삭제 동기화(--prune): 이전 적재엔 있으나 현재 없는 파일 = 삭제됨 → parquet·Neo4j 제거
    current_files = {str(f) for f in files}
    known_files = set(load_processed_files(args.product).keys())
    removed_files = compute_removed(known_files, current_files) if args.prune else []
    if removed_files:
        cached_records = [r for r in cached_records if r.get("source_file") not in set(removed_files)]
        print(f"[INFO] 삭제 동기화 대상(--prune): {len(removed_files)}개 파일")

    # 3. 청킹 — RecursiveChunker(recipe="markdown")
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
        print(f"       {f.name}: {len(raw)}청크")

    total_new = sum(len(c) for _, c in file_chunk_map)
    total_chunks = len(cached_records) + total_new
    print(f"[INFO] 총 청크: {total_chunks}개 (신규: {total_new}개)")

    if args.dry_run:
        print("\n[DRY-RUN] 임베딩·적재 없이 종료합니다.")
        if removed_files:
            print(f"[DRY-RUN] 삭제 동기화 예정(--prune): {len(removed_files)}개 파일")
        layer_counts: dict[str, int] = {}
        for f, raw in file_chunk_map:
            lyr = _extract_layer(f, prefix)
            layer_counts[lyr] = layer_counts.get(lyr, 0) + len(raw)
        for lyr, cnt in layer_counts.items():
            print(f"[DRY-RUN]   {lyr}: {cnt}청크")
        return

    # 4. 임베딩 — EmbeddingsRefinery. 모델·차원은 _embed_config 단일 출처에서 해소.
    import _embed_config as _ec
    spec = _ec.resolve_model(args.model)
    embed_dim = spec["dim"]
    model_name = spec["name"]
    all_raw_chunks = [c for _, chunks in file_chunk_map for c in chunks]

    if all_raw_chunks:
        print(f"[INFO] 임베딩 생성 중 (model={spec['key']} dim={embed_dim}, {len(all_raw_chunks)}건)...")
        embeddings_model = _build_from_spec(spec)
        refinery = EmbeddingsRefinery(embeddings=embeddings_model)
        embedded = refinery(all_raw_chunks)
        model_name = getattr(embeddings_model, "model", model_name)
    else:
        embedded = []

    # 5. 메타데이터 부착 → 레코드 생성
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

    # 6. 체크포인트 저장
    final_records = cached_records + new_records
    save_checkpoint(args.product, final_records)

    # 7. Neo4j 적재
    driver = get_driver(args.neo4j_uri, args.neo4j_user, password)
    neo4j_count = 0
    try:
        with driver.session() as session:
            print(f"[INFO] 벡터 인덱스 확인/생성 (dim={embed_dim})...")
            ensure_vector_index(session, embed_dim)
            # 수정 동기화: 재임베딩 파일의 옛 청크 + 삭제 파일 청크를 먼저 제거(유령 청크 방지).
            stale_files = sorted(set(reembed) | set(removed_files))
            if stale_files:
                deleted = delete_chunks_for_files(session, stale_files)
                print(f"[INFO] 옛/삭제 청크 제거: {deleted}개 (대상 {len(stale_files)}파일)")
            print("[INFO] :Chunk 노드 MERGE 시작...")
            neo4j_count = merge_chunks(session, final_records)
            print("[INFO] [:HAS_CHUNK] 관계 연결 시작...")
            link_chunks_to_nodes(session)
    finally:
        driver.close()

    elapsed = time.time() - start_time
    print(f"\n[완료] 소요 시간: {elapsed:.1f}초")
    print(f"[완료] 처리 파일: {len(new_files)}개 (스킵: {skip_count}개)")
    print(f"[완료] 총 청크: {total_chunks}개")
    print(f"[완료] 임베딩 모델: {model_name}")
    print(f"[완료] Neo4j (:Chunk) 노드: {neo4j_count}개")
    print(f"[완료] 청킹 라이브러리: chonkie {CHONKIE_VERSION}")


if __name__ == "__main__":
    main()
