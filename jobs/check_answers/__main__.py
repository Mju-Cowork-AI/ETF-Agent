"""CLI: python -m jobs.check_answers"""

import asyncio
import sys

from app.db import dispose_engine, get_sessionmaker
from jobs.check_answers import run


async def main() -> None:
    try:
        exit_code = await run(get_sessionmaker())
    finally:
        await dispose_engine()
    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())
