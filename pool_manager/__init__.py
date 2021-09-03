import random
import asyncio
from contextlib import asynccontextmanager

import aiopg


class PoolManager:
    DEFAULT_POLL_INTERVAL = 1

    def __init__(self, *dsn: str, poll_interval: int = DEFAULT_POLL_INTERVAL):
        self.dsn = dsn
        self.poll_interval = poll_interval
        self.master_pools = set()
        self.replica_pools = set()
        self._all_pools = set()
        self.create_pools = asyncio.create_task(self._create_pools())
        self.check_statuses = asyncio.create_task(self._check_statuses())
        self.started = False

    async def _create_pool(self, host):
        pool = await aiopg.create_pool(host)
        self._all_pools.add(pool)

    async def _create_pools(self):
        """Создание пулов"""
        tasks = [
            asyncio.create_task(self._create_pool(host))
            for host in self.dsn
        ]
        await asyncio.gather(*tasks)

    async def _set_status(self, pool, status):
        """Назначить статус пула, master/slave"""
        if not status:
            if pool in self.replica_pools:
                self.replica_pools.remove(pool)
            self.master_pools.add(pool)
        else:
            if pool in self.master_pools:
                self.master_pools.remove(pool)
            self.replica_pools.add(pool)

    @staticmethod
    async def _get_status(pool):
        """Получить статус пула, master/slave"""
        QUERY = "SELECT pg_is_in_recovery()"
        with await pool.cursor() as cur:
            await cur.execute(QUERY)
            status = await cur.fetchone()
            return status[0]

    async def _add_status(self, pool):
        status = await self._get_status(pool)
        await self._set_status(pool, status)

    async def _check_statuses(self):
        """Проверка статусов пулов"""
        while True:
            tasks = [
                asyncio.create_task(self._add_status(pool))
                for pool in self._all_pools
            ]
            await asyncio.gather(*tasks)
            await asyncio.sleep(self.poll_interval)

    @staticmethod
    def _get_random_pool(name_pool):
        """Вернуть случайный пул из name_pool"""
        return random.choice(tuple(name_pool))

    async def get_pool(self, writable: bool = True) -> aiopg.Pool:
        if writable:
            return self._get_random_pool(self.master_pools)
        return self._get_random_pool(self.replica_pools)

    @asynccontextmanager
    async def acquire(self, writable: bool = True) -> aiopg.Connection:
        if not self.started:
            await self.create_pools
            self.started = True
        await asyncio.sleep(self.poll_interval)
        pool = await self.get_pool(writable)
        async with pool.acquire() as conn:
            yield conn

    async def close(self):
        for pool in self._all_pools:
            pool.close()
            await pool.wait_closed()
        self.check_statuses.cancel()
        self.create_pools.cancel()
        self.started = False
