"""ingest: 문단 청킹(겹침), 재적재 시 갱신 (P1-DA-03)."""

from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.db import get_sessionmaker
from app.llm.fake import FakeEmbedder
from app.rag.chunker import chunk_sections, parse_markdown
from app.rag.ingest import ingest_bytes
from app.repositories import documents as doc_repo
from app.repositories.models import Chunk
from app.settings import REPO_ROOT
from jobs.ingest import resolve_target, source_uri_for
from jobs.ingest.__main__ import _normalize_prefix, _validate_prefix_vs_targets
from jobs.ingest.__main__ import main as ingest_cli


def test_markdown_chunking_with_overlap() -> None:
    para = "가" * 300
    md = f"# 제목\n\n## 섹션\n\n{para}1\n\n{para}2\n\n{para}3\n"
    title, sections = parse_markdown(md)
    chunks = chunk_sections(sections, max_chars=700, overlap_chars=100)
    assert title == "제목"
    assert len(chunks) == 2
    assert chunks[0].meta["heading"] == "섹션"
    # 두 번째 청크는 직전 청크 마지막 문단 끝 100자로 시작한다(겹침)
    assert chunks[1].content.split("\n")[1] == (para + "2")[-100:]


async def test_reingest_updates_document() -> None:
    emb = FakeEmbedder(dim=1024)
    async with get_sessionmaker()() as s:
        r1 = await ingest_bytes(
            s, emb, source_uri="test://doc.md", filename="doc.md", data=b"# A\n\n## x\n\nfirst"
        )
    async with get_sessionmaker()() as s:
        r2 = await ingest_bytes(
            s,
            emb,
            source_uri="test://doc.md",
            filename="doc.md",
            data=b"# A\n\n## x\n\nsecond\n\n## y\n\nthird",
        )
    assert (r1.status, r2.status) == ("created", "updated")
    assert r1.document_id == r2.document_id
    async with get_sessionmaker()() as s:
        doc = await doc_repo.get_document_by_uri(s, "test://doc.md")
        rows = await doc_repo.load_chunks(s, [c for c in range(1, 10_000)])
    contents = [c.content for c, _ in rows.values() if c.document_id == doc.id]
    assert sorted(contents) == ["## x\nsecond", "## y\nthird"]


def test_resolve_target_prefers_repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """레포 기준 경로를 실행 위치와 무관하게 찾는다(make ingest ARGS="data/docs")."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "README.md").write_text("# cwd")
    assert resolve_target("data/docs") == REPO_ROOT / "data/docs"
    assert resolve_target("README.md") == REPO_ROOT / "README.md"  # 실행 위치의 같은 이름보다 먼저
    (tmp_path / "only-here.md").write_text("# x")
    assert resolve_target("only-here.md") == Path("only-here.md")
    # 실행 위치를 명시하면 레포 루트로 바꾸지 않는다(`.`이 레포 전체가 되지 않게).
    assert resolve_target(".") == Path(".")
    assert resolve_target("./README.md") == Path("README.md")


def test_resolve_target_rejects_missing_path() -> None:
    with pytest.raises(FileNotFoundError):
        resolve_target("no/such/dir")


@pytest.mark.parametrize("kind", ["missing", "unsupported_file", "empty_dir", "unreadable"])
async def test_cli_fails_when_nothing_to_ingest(
    kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """없는 경로, 지원하지 않는 파일, 문서가 없는 디렉터리, 읽을 수 없는 문서는 1로 끝난다."""
    (tmp_path / "notes.toml").write_text("x = 1")
    (tmp_path / "empty").mkdir()
    (tmp_path / "broken.pdf").write_bytes(b"not a pdf")
    target = {
        "missing": tmp_path / "nope",
        "unsupported_file": tmp_path / "notes.toml",
        "empty_dir": tmp_path / "empty",
        "unreadable": tmp_path / "broken.pdf",
    }[kind]
    monkeypatch.setattr("sys.argv", ["jobs.ingest", str(target)])
    assert await ingest_cli() == 1
    out = capsys.readouterr().out
    assert out
    if kind == "unreadable":
        assert "broken.pdf" in out


# ---------- --delete-prefix ----------


async def test_delete_prefix_removes_only_matching_docs() -> None:
    """--delete-prefix로 샘플 경로 문서만 지워지고, 다른 경로·업로드 문서는 남는다."""
    emb = FakeEmbedder(dim=1024)
    maker = get_sessionmaker()
    uris = [
        "file://data/samples/docs/a.md",
        "file://data/real/b.md",
        "local://uploads/c.md",
    ]
    # 세 문서 적재
    for uri in uris:
        async with maker() as s:
            await ingest_bytes(s, emb, source_uri=uri, filename="x.md", data=b"# T\n\n## S\n\nbody")

    # 삭제 전 chunks 확인
    async with maker() as s:
        doc_sample = await doc_repo.get_document_by_uri(s, uris[0])
        assert doc_sample is not None
        sample_chunk_count = await s.scalar(
            select(func.count(Chunk.id)).where(Chunk.document_id == doc_sample.id)
        )
        assert sample_chunk_count and sample_chunk_count > 0

    # prefix 삭제
    async with maker() as s:
        deleted = await doc_repo.delete_documents_by_prefix(s, "data/samples/docs")
        await s.commit()

    assert deleted == 1

    # 삭제된 문서와 chunks 확인
    async with maker() as s:
        assert await doc_repo.get_document_by_uri(s, uris[0]) is None
        remaining_chunks = await s.scalar(
            select(func.count(Chunk.id)).where(Chunk.document_id == doc_sample.id)
        )
        assert remaining_chunks == 0

    # 나머지 문서 존재 확인
    async with maker() as s:
        assert await doc_repo.get_document_by_uri(s, uris[1]) is not None
        assert await doc_repo.get_document_by_uri(s, uris[2]) is not None


def test_normalize_prefix_strips_slashes_and_whitespace() -> None:
    assert _normalize_prefix("  data/samples/docs/  ") == "data/samples/docs"
    assert _normalize_prefix("/data/samples/docs/") == "data/samples/docs"


def test_normalize_prefix_rejects_empty() -> None:
    with pytest.raises(ValueError, match="비어"):
        _normalize_prefix("   ")
    with pytest.raises(ValueError, match="비어"):
        _normalize_prefix("///")


def test_validate_prefix_rejects_overlapping_target() -> None:
    # 상대 경로 → resolve_target이 REPO_ROOT / "data/docs"로 풀린다
    resolved = [REPO_ROOT / "data/docs"]
    with pytest.raises(ValueError, match="포함"):
        _validate_prefix_vs_targets("data", resolved)
    with pytest.raises(ValueError, match="포함"):
        _validate_prefix_vs_targets("data/docs", resolved)


def test_validate_prefix_rejects_overlapping_absolute_target() -> None:
    """절대 경로(/workspace/data/docs 등)도 source_uri 변환 후 겹침을 잡는다."""
    resolved = [REPO_ROOT / "data/docs"]
    # source_uri_for(REPO_ROOT / "data/docs") == "file://data/docs"
    assert source_uri_for(resolved[0]) == "file://data/docs"
    with pytest.raises(ValueError, match="포함"):
        _validate_prefix_vs_targets("data/docs", resolved)


def test_validate_prefix_allows_sibling_paths() -> None:
    resolved = [REPO_ROOT / "data/docs"]
    _validate_prefix_vs_targets("data/samples/docs", resolved)
