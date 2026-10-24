import asyncio
import os

import asyncpg
from dotenv import load_dotenv


load_dotenv()


DATABASE_URL = os.getenv(
    "DATABASE_URL"
)


async def test_database():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not configured"
        )

    connection = await asyncpg.connect(
        DATABASE_URL
    )

    try:
        result = await connection.fetchval(
            "SELECT 1"
        )

        print(
            f"PostgreSQL connection successful: "
            f"{result}"
        )

    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(
        test_database()
    )