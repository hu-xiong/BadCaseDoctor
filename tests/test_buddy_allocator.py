# -*- coding: utf-8 -*-
from memory.buddy_allocator import BuddyAllocator


def test_buddy_alloc_free_roundtrip():
    ba = BuddyAllocator(max_order=6, capacity_frames=64)
    start, order = ba.alloc(3)
    assert start == 0
    assert (1 << order) >= 3
    ba.free(start, order)
    start2, order2 = ba.alloc(3)
    assert (1 << order2) >= 3


def test_buddy_hash_index():
    ba = BuddyAllocator(max_order=4, capacity_frames=16)
    ba.register_hash("abc", 2)
    assert ba.lookup_hash("abc") == 2


def test_buddy_split_larger_block():
    ba = BuddyAllocator(max_order=4, capacity_frames=16)
    start, order = ba.alloc(1)
    assert (1 << order) == 1
    ba.free(start, order)
    s2, o2 = ba.alloc(5)
    assert (1 << o2) >= 5


def test_buddy_release_and_evict():
    ba = BuddyAllocator(max_order=4, capacity_frames=16)
    ba.register_hash("h1", 0)
    ba._frames[0].ref_count = 2
    ba.release_hash("h1")
    assert ba._frames[0].ref_count == 1
    ba.release_hash("h1")
    assert ba._frames[0].ref_count == 0
    ba.maybe_evict(max_cold_frames=0)
