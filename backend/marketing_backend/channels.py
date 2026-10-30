"""Narrow delivery adapters. Social and messaging have no live integration."""
from dataclasses import dataclass
import os
from typing import Protocol
from .stage_contracts import content_hash


@dataclass(frozen=True)
class Receipt:
    reference: str


class ChannelAdapter(Protocol):
    def handoff(self, delivery) -> Receipt: ...


class AdapterUnavailable(Exception):
    pass


class FakeAdapter:
    """Deterministic synthetic receipt; never performs network I/O."""
    def __init__(self, channel):
        self.channel = channel

    def handoff(self, delivery):
        if delivery.channel != self.channel:
            raise AdapterUnavailable()
        return Receipt("synthetic:"+str(delivery.id)+":"+content_hash(delivery.snapshot))


def adapter_for(channel):
    # Explicit test configuration; arbitrary adapter imports are never accepted.
    if channel in ("LINKEDIN", "MESSAGING") and os.getenv("DELIVERY_ADAPTER_MODE") == "synthetic" and os.getenv("APP_ENV") in ("test", "local-smoke", "native-acceptance"):
        return FakeAdapter(channel)
    raise AdapterUnavailable()
