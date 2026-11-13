"""
PitchPulse 2026 - Bounded LRU Cache & Efficiency Utilities
Provides memory-safe caching, deterministic routing, and string normalization for AI operations.
"""

import hashlib
import logging
import re
import time
from collections import OrderedDict
from functools import lru_cache
from typing import Any

logger = logging.getLogger("pitchpulse.cache")

# Bounded TTL Cache: max 256 entries, 60-second expiry
_MAX_CACHE_ENTRIES = 256
_TTL_SECONDS = 60
_CACHE: OrderedDict = OrderedDict()


def cache_key_for_prompt(prompt: str, lang: str, role: str) -> str:
    """Generates a collision-resistant SHA-256 cache key for prompt text, language, and role."""
    normalized = f"{prompt.strip().lower()}:{lang.strip().lower()}:{role.strip().lower()}"
    return f"ai_resp_{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:32]}"


def timed_cache_set(key: str, value: Any) -> None:
    """Stores a value with TTL evicting oldest entries when bound is exceeded."""
    _evict_expired()
    if len(_CACHE) >= _MAX_CACHE_ENTRIES:
        _CACHE.popitem(last=False)  # Evict oldest (LRU)
    _CACHE[key] = (time.monotonic(), value)
    logger.debug("Cache SET: %s (size=%d)", key, len(_CACHE))


def timed_cache_get(key: str) -> Any | None:
    """Returns cached value if still within TTL, else returns None."""
    entry = _CACHE.get(key)
    if entry is None:
        return None
    cached_at, value = entry
    if time.monotonic() - cached_at > _TTL_SECONDS:
        del _CACHE[key]
        logger.debug("Cache EXPIRED: %s", key)
        return None
    logger.debug("Cache HIT: %s", key)
    return value


def _evict_expired() -> int:
    """Garbage-collects all expired keys. Returns number evicted."""
    now = time.monotonic()
    expired = [k for k, (t, _) in _CACHE.items() if now - t > _TTL_SECONDS]
    for k in expired:
        del _CACHE[k]
    if expired:
        logger.debug("Cache evicted %d expired entries", len(expired))
    return len(expired)


def reset_cache() -> None:
    """Purges all entries from the active cache for test isolation."""
    _CACHE.clear()


def cache_stats() -> dict:
    """Returns cache diagnostic metadata for health endpoint."""
    _evict_expired()
    return {
        "active_entries": len(_CACHE),
        "max_entries": _MAX_CACHE_ENTRIES,
        "ttl_seconds": _TTL_SECONDS,
    }


@lru_cache(maxsize=256)
def parse_section_number(section_code: str) -> int:
    """
    Extracts integer section number via regex. Fixes section '104' parsed as '10' issue.
    Uses LRU cache for fast repeated lookups.
    """
    match = re.search(r"\d+", section_code)
    return int(match.group()) if match else 100


@lru_cache(maxsize=256)
def calculate_optimal_path(section_code: str, mobility_profile: str) -> tuple[str, str, str, int]:
    """
    Deterministic routing using integer section parser.
    Ensures accessibility profiles route via dedicated step-free facilities.
    Returns (gate, elevator, quiet_room, walk_minutes).
    """
    sec_num = parse_section_number(section_code)

    if mobility_profile in ("wheelchair", "low_mobility"):
        gate = "Gate B (East Accessible Concourse) — MetLife Stadium"
        elevator = "Elevator Bank 2 (North ADA Tower)"
        quiet_room = "Sensory Quiet Suite #2 (North Mezzanine Level 2)"
        walk_time = max(3, 3 + (sec_num % 5))
    elif mobility_profile == "sensory_sensitive":
        gate = "Gate C (Low-Sensory South Concourse) — MetLife Stadium"
        elevator = "Elevator Bank 1 (South Tower)"
        quiet_room = "Sensory Quiet Suite #1 (South Mezzanine Level 2) — Noise-cancelling headsets provided"
        walk_time = max(4, 4 + (sec_num % 4))
    else:
        gate = "Gate A (Main North Plaza) — MetLife Stadium"
        elevator = "Escalator Bank East — Level 1 to 3"
        quiet_room = "Family Comfort Room (Section 108, Level 1)"
        walk_time = max(3, 2 + (sec_num % 6))

    return gate, elevator, quiet_room, walk_time
