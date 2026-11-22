"""CLI: python -m jobs.ingest [경로...] [--force] [--doc-type faq] [--delete-prefix <경로>]"""

import argparse
import asyncio
from pathlib import Path

from app.db import dispose_engine, get_sessionmaker
from app.llm import build_embedder
from app.llm.base import LLMError
from app.rag.ingest import SUPPORTED_SUFFIXES
from app.repositories.documents import delete_documents_by_prefix
from app.settings import REPO_ROOT, get_settings
from jobs.ingest import collect_files, ingest_paths, resolve_target, source_uri_for


def _normalize_prefix(raw: str) -> str:
    """앞뒤 공백·슬래시를 떼고 빈 값이면 ValueError."""
    cleaned = raw.strip().strip("/").strip()
    if not cleaned:
        raise ValueError("--delete-prefix 값이 비어 있습니다.")
    return cleaned


def _validate_prefix_vs_targets(prefix: str, resolved_targets: list[Path]) -> None:
    """적재 대상의 source_uri가 file://<prefix>/ 아래이면 ValueError."""
    delete_uri_prefix = f"file://{prefix}/"
    for target in resolved_targets:
        uri = source_uri_for(target)
        if uri.startswith(delete_uri_prefix) or uri == f"file://{prefix}":
            raise ValueError(
                f"--delete-prefix '{prefix}'가 적재 대상 '{target}'를 포함합니다. "
                f"적재할 경로와 삭제할 경로가 겹치지 않아야 합니다."
            )


async def main() -> int:
    parser = argparse.ArgumentParser(description="문서 ingest (PDF·마크다운)")
    parser.add_argument("paths", nargs="*", default=[str(REPO_ROOT / "data/docs")])
    parser.add_argument("--force", action="store_true", help="내용이 같아도 다시 임베딩")
    parser.add_argument("--doc-type", default="faq")
    parser.add_argument(
        "--delete-prefix",
        default=None,
        help="적재 전에 source_uri가 file://<경로>/로 시작하는 문서를 삭제",
    )
    args = parser.parse_args()

    # --delete-prefix 정규화 (경로 검증은 resolve_target 뒤에)
    if args.delete_prefix is not None:
        try:
            prefix = _normalize_prefix(args.delete_prefix)
        except ValueError as e:
            print(f"오류: {e}")
            return 1
    else:
        prefix = None

    try:
        targets = [resolve_target(p) for p in args.paths]
    except FileNotFoundError as e:
        print(
            f"경로를 찾을 수 없습니다: {e}\n"
            f"→ 레포 루트({REPO_ROOT}) 기준 상대 경로나 컨테이너 안의 절대 경로를 주세요."
        )
        return 1

    # --delete-prefix: resolve된 경로의 source_uri로 겹침 검증
    if prefix is not None:
        try:
            _validate_prefix_vs_targets(prefix, targets)
        except ValueError as e:
            print(f"오류: {e}")
            return 1
    empty = [str(t) for t in targets if not collect_files(t)]
    if empty:
        print(
            f"적재할 문서가 없습니다: {', '.join(empty)}\n→ 지원 형식: {', '.join(SUPPORTED_SUFFIXES)}"
        )
        return 1

    settings = get_settings()
    embedder = build_embedder(settings)
    print(f"임베딩: provider={settings.embedding_provider} model={embedder.model}")

    # --delete-prefix: 적재 전에 기존 문서 삭제
    if prefix is not None:
        maker = get_sessionmaker()
        async with maker() as session:
            deleted = await delete_documents_by_prefix(session, prefix)
            await session.commit()
        print(f"삭제: {deleted}개 문서 (prefix: file://{prefix}/)")
    try:
        for target in targets:
            for r in await ingest_paths(
                get_sessionmaker(),
                embedder,
                target,
                doc_type=args.doc_type,
                force=args.force,
            ):
                n = "-" if r.chunks < 0 else r.chunks
                print(f"  [{r.status:9}] {r.title}  chunks={n}  ({r.source_uri})")
    except LLMError as e:
        print(
            f"임베딩 실패: {e}\n→ LLM_API_KEY·EMBEDDING_MODEL({settings.embedding_model})·네트워크를 확인하세요."
        )
        return 1
    except ValueError as e:  # 읽을 수 없는 문서(손상된 PDF, 빈 본문 등). 이 파일에서 멈춘다.
        print(f"문서를 적재하지 못해 중단합니다: {e}")
        return 1
    finally:
        await dispose_engine()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
