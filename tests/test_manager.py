import asyncio

import aiopg
import pytest

from pool_manager import PoolManager


@pytest.fixture
async def proxy1(tcp_proxy):
    proxy = tcp_proxy("localhost", 5432)
    try:
        await proxy.start()
        yield proxy
    finally:
        await proxy.close()


@pytest.fixture
async def proxy2(tcp_proxy):
    proxy = tcp_proxy("localhost", 5433)
    try:
        await proxy.start()
        yield proxy
    finally:
        await proxy.close()


async def assert_is_master(conn: aiopg.Connection, is_master: bool):
    """
    SELECT pg_is_in_recovery() is the same as SELECT transaction_read_only,
    but is more reliable.
    """
    async with conn.cursor() as cur:
        await cur.execute("SELECT pg_is_in_recovery()")
        assert await cur.fetchone() == (not is_master, )


async def test_master_replica_switch(proxy1, proxy2):
    dsns = [
        f"postgresql://user:hackme@{server}/mydb"
        for server in (
            f"{proxy1.proxy_host}:{proxy1.proxy_port}",
            f"{proxy2.proxy_host}:{proxy2.proxy_port}",
        )
    ]

    poll_interval = 1
    pm = PoolManager(*dsns, poll_interval=poll_interval)

    async with pm.acquire(writable=True) as conn:
        assert conn.raw.info.port == proxy1.proxy_port
        await assert_is_master(conn, True)

    async with pm.acquire(writable=False) as conn:
        assert conn.raw.info.port == proxy2.proxy_port
        await assert_is_master(conn, False)

    # Change master & replica behind proxy
    proxy1.target_port, proxy2.target_port = (
        proxy2.target_port, proxy1.target_port,
    )
    await proxy1.disconnect_all()
    await proxy2.disconnect_all()
    await asyncio.sleep(poll_interval * 2)

    async with pm.acquire(writable=True) as conn:
        assert conn.raw.info.port == proxy2.proxy_port
        await assert_is_master(conn, True)

    async with pm.acquire(writable=False) as conn:
        assert conn.raw.info.port == proxy1.proxy_port
        await assert_is_master(conn, False)

    await pm.close()
