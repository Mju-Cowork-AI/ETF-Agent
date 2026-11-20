"""CLI: python -m jobs.load_real [CSV 경로]"""

import asyncio
import sys
from pathlib import Path

from app.db import dispose_engine, get_sessionmaker
from jobs.load_real import REAL_DIR, run


async def main() -> None:
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else REAL_DIR / "etf_master.csv"
    try:
        result = await run(get_sessionmaker(), csv_path)
    finally:
        await dispose_engine()
    print("실데이터 적재 완료:", ", ".join(f"{k}={v}" for k, v in result.items()))


if __name__ == "__main__":
    asyncio.run(main())
