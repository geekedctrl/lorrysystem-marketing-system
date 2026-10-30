"""Code-owned routing. One process selects exactly one shared pool."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Pool:
    name: str
    kind: str
    stages: tuple[str, ...] = ()
    channels: tuple[str, ...] = ()


STAGES = ("SETUP", "DISCOVERY", "RESEARCH", "CONTACT_SEARCH", "SCORING", "MATCHING", "DRAFTING")
POOLS = {name: Pool(name, "stage", (name,)) for name in STAGES}
POOLS.update(
    EMAIL=Pool("EMAIL", "delivery", channels=("EMAIL",)),
    SOCIAL=Pool("SOCIAL", "delivery", channels=("LINKEDIN",)),
    MESSAGING=Pool("MESSAGING", "delivery", channels=("MESSAGING",)),
    SCHEDULER=Pool("SCHEDULER", "scheduler"),
)


def get_pool(name):
    if not isinstance(name, str) or name not in POOLS:
        raise ValueError("Select one known worker pool")
    return POOLS[name]


def stage_pool(stage):
    return stage if stage in STAGES else "LEGACY"


def channel_pool(channel):
    return {"EMAIL": "EMAIL", "LINKEDIN": "SOCIAL", "MESSAGING": "MESSAGING"}[channel]
