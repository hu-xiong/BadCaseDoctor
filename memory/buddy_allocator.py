# -*- coding: utf-8 -*-
"""本地页帧伙伴分配器（应用进程内，与 GPU KV block 无关）。"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class PageFrame:
    frame_id: int
    content_hash: str = ""
    ref_count: int = 0
    last_used_at: float = 0.0
    flags: int = 0


@dataclass
class BuddyAllocator:
    """2^order 页帧块分配；VPN 槽连续，物理 frame 不要求连续。"""

    max_order: int = 10
    capacity_frames: int = 1024
    _free_lists: Dict[int, List[int]] = field(default_factory=dict)
    _frames: Dict[int, PageFrame] = field(default_factory=dict)
    _hash_index: Dict[str, int] = field(default_factory=dict)
    _next_frame_id: int = 0
    _clock: float = 0.0

    def __post_init__(self) -> None:
        for o in range(self.max_order + 1):
            self._free_lists[o] = []
        n = min(self.capacity_frames, 1 << self.max_order)
        self._free_lists[self._order_for(n)].append(0)
        for fid in range(n):
            self._frames[fid] = PageFrame(frame_id=fid)

    def alloc(self, n_pages: int) -> Tuple[int, int]:
        if n_pages <= 0:
            raise ValueError("n_pages must be positive")
        need = 1 << self._ceil_log2(n_pages)
        order = int(math.log2(need))
        while order <= self.max_order:
            if self._free_lists[order]:
                start = self._free_lists[order].pop(0)
                final_order = self._split_down(start, order, need)
                return start, final_order
            order += 1
        raise MemoryError(f"buddy alloc failed: n_pages={n_pages}")

    def free(self, start_slot: int, order: int) -> None:
        self._free_lists[order].append(start_slot)
        self._coalesce(start_slot, order)

    def register_hash(self, content_hash: str, frame_id: int) -> None:
        if content_hash:
            self._hash_index[content_hash] = frame_id

    def lookup_hash(self, content_hash: str) -> Optional[int]:
        fid = self._hash_index.get(content_hash)
        return fid

    def touch(self, frame_id: int) -> None:
        self._clock += 1.0
        if frame_id in self._frames:
            self._frames[frame_id].last_used_at = self._clock
            self._frames[frame_id].ref_count += 1

    def release_hash(self, content_hash: str) -> None:
        if not content_hash:
            return
        fid = self._hash_index.get(content_hash)
        if fid is None or fid not in self._frames:
            return
        fr = self._frames[fid]
        fr.ref_count = max(0, fr.ref_count - 1)

    def maybe_evict(self, *, max_cold_frames: int = 256) -> int:
        """淘汰 ref_count=0 的冷页帧，返回淘汰数量。"""
        cold = sum(1 for fr in self._frames.values() if fr.ref_count <= 0)
        evicted = 0
        while cold > max_cold_frames:
            fid = self.evict_lru(skip_pinned=True)
            if fid is None:
                break
            evicted += 1
            cold -= 1
        return evicted

    def evict_lru(self, *, skip_pinned: bool = True) -> Optional[int]:
        candidates = [
            (fr.last_used_at, fid)
            for fid, fr in self._frames.items()
            if fr.ref_count <= 0
            and (not skip_pinned or not (fr.flags & 1))
        ]
        if not candidates:
            return None
        candidates.sort()
        _, fid = candidates[0]
        fr = self._frames[fid]
        if fr.content_hash and self._hash_index.get(fr.content_hash) == fid:
            self._hash_index.pop(fr.content_hash, None)
        fr.content_hash = ""
        return fid

    def _split_down(self, start: int, order: int, need: int) -> int:
        while (1 << order) > need and order > 0:
            order -= 1
            buddy = start + (1 << order)
            self._free_lists[order].append(buddy)
        return order

    def _coalesce(self, start: int, order: int) -> None:
        while order < self.max_order:
            buddy = start ^ (1 << order)
            lst = self._free_lists[order]
            if buddy not in lst:
                break
            lst.remove(buddy)
            start = min(start, buddy)
            order += 1
            self._free_lists[order].append(start)

    @staticmethod
    def _ceil_log2(n: int) -> int:
        if n <= 1:
            return 0
        return (n - 1).bit_length()

    def _order_for(self, n: int) -> int:
        return self._ceil_log2(max(1, n))
