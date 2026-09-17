"""Overlap bounded network preparation with single-device inference."""
from collections import deque
from concurrent.futures import ThreadPoolExecutor


def prefetched(items, prepare, depth=2):
    if depth < 1:
        raise ValueError('Prefetch depth must be positive')
    iterator = iter(items)
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix='sar-download') as pool:
        pending = deque()
        def enqueue():
            try:
                item = next(iterator)
            except StopIteration:
                return
            pending.append((item, pool.submit(prepare, item)))
        for _ in range(depth):
            enqueue()
        try:
            while pending:
                item, future = pending.popleft()
                try:
                    value, error = future.result(), None
                except Exception as exc:
                    value, error = None, exc
                enqueue()
                yield item, value, error
        finally:
            for _, future in pending:
                future.cancel()
