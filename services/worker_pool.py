"""
Worker Pool implementation for managing concurrent course queries.

This module provides a WorkerPool class that manages a fixed number of
async workers to process course query tasks efficiently, avoiding the
"one task per course" resource exhaustion problem.
"""

import asyncio
from typing import Callable, Any


class WorkerPool:
    """
    非同步 Worker Pool - 避免「每課程一任務」的資源耗盡問題

    使用固定數量的 Worker 處理課程查詢任務，而非為每個課程建立獨立任務。
    這可以有效控制並行數量，避免記憶體耗盡。
    """

    def __init__(self, size: int = 5):
        """
        初始化 Worker Pool

        Args:
            size: Worker 數量（預設 5 個）
        """
        self.size = size
        self.queue = asyncio.Queue()
        self.workers = []
        self.running = False

    async def start(self):
        """啟動 Worker Pool"""
        self.running = True
        for i in range(self.size):
            worker = asyncio.create_task(self._worker(i))
            self.workers.append(worker)

    async def stop(self):
        """停止 Worker Pool"""
        self.running = False
        # 發送停止信號給所有 Worker
        for _ in range(self.size):
            await self.queue.put(None)  # Sentinel value
        # 等待所有 Worker 完成
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()

    async def submit(self, func: Callable, *args, **kwargs) -> Any:
        """
        提交任務到佇列並等待執行結果

        Args:
            func: 要執行的非同步函數
            *args: 函數參數
            **kwargs: 函數關鍵字參數

        Returns:
            函數執行結果
        """
        future = asyncio.Future()
        await self.queue.put((future, func, args, kwargs))
        return await future

    async def _worker(self, worker_id: int):
        """
        Worker 執行緒

        Args:
            worker_id: Worker 編號（用於除錯）
        """
        while self.running:
            item = await self.queue.get()

            # 檢查停止信號
            if item is None:
                break

            future, func, args, kwargs = item
            try:
                # 執行任務
                result = await func(*args, **kwargs)
                future.set_result(result)
            except Exception as e:
                # 將錯誤傳回給呼叫者
                future.set_exception(e)
            finally:
                self.queue.task_done()
