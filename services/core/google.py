"""Google adapter factory. Fixture while LIVE_EFFECTS_ENABLED is false; D2's real adapter when present."""

from __future__ import annotations

from services.core.config import Settings
from services.core.contracts.google_adapter import GoogleAdapter
from services.core.testing.fixture_google_adapter import FixtureGoogleAdapter, FixtureMode


def build_google_adapter(settings: Settings, *, mode: FixtureMode = "ok") -> GoogleAdapter:
    if not settings.live_effects_enabled:
        return FixtureGoogleAdapter(mode=mode)
    try:
        from services.adapters.google import build_adapter
    except ImportError as exc:
        raise RuntimeError(
            "LIVE_EFFECTS_ENABLED=true but services.adapters.google.build_adapter is not available"
        ) from exc
    return build_adapter(settings)
