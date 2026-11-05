"""Generate contracts/openapi.json and contracts/schemas/*.json. Run: python -m services.core.contracts.export"""

import json
from pathlib import Path

from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from . import google_adapter, requests, views
from .envelopes import ErrorEnvelope
from .version import CONTRACT_VERSION, PLANNING_BASELINE

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_DIR = REPO_ROOT / "contracts"

ROOT_MODELS: list[type[BaseModel]] = [
    ErrorEnvelope,
    views.HealthLive,
    views.Usage,
    views.CampaignView,
    views.MissionDetail,
    views.ProspectCase,
    views.EvidenceView,
    views.DecisionView,
    views.ConversationView,
    views.MessageView,
    views.Slot,
    views.BookingReceipt,
    views.Handoff,
    requests.Limits,
    requests.CampaignCreate,
    requests.ControlInput,
    requests.ResolveInput,
    google_adapter.GoogleFailure,
    google_adapter.GoogleConnectionRef,
    google_adapter.OutboundEmail,
    google_adapter.GmailSendReceipt,
    google_adapter.ThreadPoll,
    google_adapter.ReconcileResult,
    google_adapter.FreeBusyResult,
    google_adapter.CalendarEventRequest,
    google_adapter.CalendarEventReceipt,
    google_adapter.CalendarEventLookup,
    google_adapter.OAuthStart,
    google_adapter.OAuthStartResult,
    google_adapter.ConnectionSummary,
]


def _dump(document: dict) -> str:
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def build_openapi() -> dict:
    from services.api.main import create_app

    document = create_app().openapi()
    _, defs = models_json_schema(
        [(model, "validation") for model in ROOT_MODELS],
        ref_template="#/components/schemas/{model}",
    )
    schemas = document.setdefault("components", {}).setdefault("schemas", {})
    for name, schema in defs.get("$defs", {}).items():
        schemas.setdefault(name, schema)
    document["info"]["x-contract-version"] = CONTRACT_VERSION
    document["info"]["x-planning-baseline"] = PLANNING_BASELINE
    return document


def build_exports() -> dict[Path, str]:
    files = {CONTRACTS_DIR / "openapi.json": _dump(build_openapi())}
    for model in ROOT_MODELS:
        schema = model.model_json_schema(mode="validation")
        schema["$id"] = f"urn:outcome:{CONTRACT_VERSION}:{model.__name__}"
        files[CONTRACTS_DIR / "schemas" / f"{model.__name__}.json"] = _dump(schema)
    return files


def main() -> None:
    for path, content in build_exports().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        print(path.relative_to(REPO_ROOT))


if __name__ == "__main__":
    main()
