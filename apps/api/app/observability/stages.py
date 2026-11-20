"""요청 1건의 단계별 소요 시간. 단계 이름과 시간만 다룬다(질의 원문·답변 문구 없음)."""

import time
from typing import Any

PREPARE_STAGE = "prepare"  # 하루 질문 상한 확인, 대화·질문 저장 등 그래프가 시작되기 전까지


class StageTimer:
    """단계가 바뀔 때마다 mark()를 부르면, 앞 단계의 시간을 닫고 새 단계를 시작한다.

    한 단계의 시간은 '그 단계가 시작된 때부터 다음 단계가 시작될 때(또는 stop())까지'다.
    같은 단계가 다시 나오면(재작성 뒤의 생성·검증 등) 합치지 않고 실행 순서대로 따로 남긴다.
    """

    def __init__(self, started: float, first: str = PREPARE_STAGE) -> None:
        self._stage: str | None = first
        self._at = started
        self._timings: list[dict[str, Any]] = []

    def mark(self, stage: str) -> None:
        now = time.perf_counter()
        self._close(now)
        self._stage, self._at = stage, now

    def stop(self) -> list[dict[str, Any]]:
        """마지막 단계를 닫고 전체 목록을 돌려준다. 그 뒤의 mark()는 새 단계로 이어진다."""
        self._close(time.perf_counter())
        self._stage = None
        return list(self._timings)

    def _close(self, now: float) -> None:
        if self._stage is not None:
            self._timings.append({"stage": self._stage, "ms": int((now - self._at) * 1000)})
