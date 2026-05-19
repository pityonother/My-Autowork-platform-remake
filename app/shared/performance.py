from __future__ import annotations

import copy
import hashlib
import logging
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TypeVar


T = TypeVar("T")
LOGGER = logging.getLogger("app.performance")
MAX_FILE_CACHE_ENTRIES = 64
_FILE_RESULT_CACHE: OrderedDict[tuple[str, str, Hashable], Any] = OrderedDict()


def file_sha256(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cached_file_result(
    namespace: str,
    path: Path,
    loader: Callable[[], T],
    *,
    extra_key: Hashable = "",
) -> T:
    key = (namespace, file_sha256(path), extra_key)
    if key in _FILE_RESULT_CACHE:
        _FILE_RESULT_CACHE.move_to_end(key)
        return copy.deepcopy(_FILE_RESULT_CACHE[key])

    result = loader()
    _FILE_RESULT_CACHE[key] = copy.deepcopy(result)
    while len(_FILE_RESULT_CACHE) > MAX_FILE_CACHE_ENTRIES:
        _FILE_RESULT_CACHE.popitem(last=False)
    return result


@contextmanager
def timed_step(label: str, logger: logging.Logger | None = None) -> Iterator[None]:
    target_logger = logger or LOGGER
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        target_logger.info("timing.%s elapsed_ms=%.1f", label, elapsed_ms)
