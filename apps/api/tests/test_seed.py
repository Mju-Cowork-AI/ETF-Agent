"""샘플 시드: 다시 돌려도 행이 늘지 않는다 (P1-DA-02)."""

from jobs.seed import disclosure_external_id


def test_external_id_from_url_or_content() -> None:
    """disclosure_external_id 유틸은 나중에 실데이터에서 쓸 수 있으므로 테스트를 남겨둔다."""
    row = {"ticker": "900010", "title": "[샘플] 분배금 공시", "disclosed_at": "2026-11-01"}
    assert disclosure_external_id({**row, "url": "https://example.com/d/sample-0001"}) == (
        "sample-0001"
    )
    no_url = disclosure_external_id({**row, "url": None})
    assert no_url.startswith("sample-") and no_url == disclosure_external_id({**row, "url": ""})
    assert no_url != disclosure_external_id({**row, "title": "[샘플] 다른 공시", "url": None})
