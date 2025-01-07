# app/core/shared.py

import asyncio
from typing import Set, List

# Shared Variables
subscribed_symbols: Set[str] = set()
current_batch: Set[str] = set()
batches: List[List[str]] = []
batch_cycle = None

# Synchronization Lock
subscription_lock = asyncio.Lock()
