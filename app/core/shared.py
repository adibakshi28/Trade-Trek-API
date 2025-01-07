# app/core/shared.py

import asyncio
from typing import Set, List

# Active Shared Variables
active_subscribed_symbols: Set[str] = set()
active_current_batch: Set[str] = set()
active_batches: List[List[str]] = []
active_batch_cycle = None

# Active Synchronization Lock
active_subscription_lock = asyncio.Lock()


# Dormant Shared Variables
dormant_subscribed_symbols: Set[str] = set()
dormant_current_batch: Set[str] = set()
dormant_batches: List[List[str]] = []
dormant_batch_cycle = None

# Dormant Synchronization Lock
dormant_subscription_lock = asyncio.Lock()
