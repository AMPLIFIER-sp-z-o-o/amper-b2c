from __future__ import annotations


def upgrade(from_version: str, to_version: str, plugin):
    # Plugin-specific migration hook. Keep idempotent.
    return None


def downgrade(from_version: str, to_version: str, plugin):
    # Reverse of upgrade for rollback safety.
    return None
