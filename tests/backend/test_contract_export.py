from services.core.contracts.export import REPO_ROOT, build_exports


def test_committed_contract_exports_are_up_to_date():
    stale = [
        str(path.relative_to(REPO_ROOT))
        for path, content in build_exports().items()
        if not path.exists() or path.read_text() != content
    ]

    assert not stale, f"run `python -m services.core.contracts.export`; stale: {stale}"
