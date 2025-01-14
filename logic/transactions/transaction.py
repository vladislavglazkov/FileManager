from __future__ import annotations
import asyncio
import os
import shutil
from typing import *
from logic.permissions import FilePermissions
from logic.selection import Selection
from logic.workspacemanager import WorkspaceManager


class Transaction:
    def __init__(self) -> None:
        pass

    async def execute(self, progress_callback: None |
                      Callable = None) -> None | str:
        raise NotImplementedError()

    def revert(self) -> Transaction:
        raise NotImplementedError()

    @staticmethod
    def reports_progress() -> bool:
        return False


def calc_size(path: str) -> int:
    if not os.path.exists(path):
        return 0
    if not os.path.isdir(path):
        return os.path.getsize(path)
    ans = 0
    for curdir, subdirs, subfiles in os.walk(path):
        for hh in subdirs + subfiles:
            ans += os.path.getsize(os.path.join(curdir, hh))
    return ans


def calc_total_size(paths: Iterable[str]) -> int:
    csum = 0
    for h in paths:
        csum += calc_size(h)
    return csum


class DoNothingTransaction(Transaction):
    def __init__(self) -> None:

        super().__init__()

    async def execute(self) -> None | str:
        pass

    def revert(self) -> Transaction:
        return DoNothingTransaction()
