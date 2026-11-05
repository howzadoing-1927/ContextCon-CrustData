import os
from uuid import uuid4

import pytest

from conftest import auth_headers, campaign_body, launch, mint_token


def test_missing_token_is_401(api, make_tenant):
    tenant = make_tenant()

    response = api.get(f"/api/v1/campaigns/{uuid4()}", headers={"X-Organization-ID": str(tenant.organization_id)})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_tampered_token_is_401(api, make_tenant):
    tenant = make_tenant()
    header, payload, signature = tenant.owner.token.split(".")
    tampered = f"{header}.{payload}.{signature[:-4]}{'AAAA' if not signature.endswith('AAAA') else 'BBBB'}"
    headers = {"Authorization": f"Bearer {tampered}", "X-Organization-ID": str(tenant.organization_id)}

    assert api.get(f"/api/v1/campaigns/{uuid4()}", headers=headers).status_code == 401


def test_unsigned_token_is_401(api, make_tenant):
    tenant = make_tenant()
    header, payload, _ = tenant.owner.token.split(".")
    unsigned = "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0." + payload + "."
    headers = {"Authorization": f"Bearer {unsigned}", "X-Organization-ID": str(tenant.organization_id)}

    assert api.get(f"/api/v1/campaigns/{uuid4()}", headers=headers).status_code == 401


def test_expired_token_is_401(api, make_tenant):
    if not os.environ.get("SUPABASE_JWT_SECRET"):
        pytest.skip("minting an expired token needs SUPABASE_JWT_SECRET")
    tenant = make_tenant()
    expired = mint_token(tenant.owner.id, expires_in=-120)
    headers = {"Authorization": f"Bearer {expired}", "X-Organization-ID": str(tenant.organization_id)}

    assert api.get(f"/api/v1/campaigns/{uuid4()}", headers=headers).status_code == 401


def test_missing_org_header_is_400(api, make_tenant):
    tenant = make_tenant()

    response = api.get(f"/api/v1/campaigns/{uuid4()}", headers={"Authorization": f"Bearer {tenant.owner.token}"})

    assert response.status_code == 400


def test_member_of_other_org_is_403_and_enqueues_nothing(api, make_tenant, conn):
    tenant_a, tenant_b = make_tenant(), make_tenant()

    response = api.post(
        "/api/v1/campaigns",
        headers=auth_headers(tenant_a.owner, tenant_b.organization_id, key="cross-tenant"),
        json=campaign_body(tenant_b),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    count = conn.execute(
        "select count(*) as n from campaigns where organization_id = %s", (tenant_b.organization_id,)
    ).fetchone()["n"]
    assert count == 0


def test_foreign_campaign_id_is_404(api, make_tenant, database_url):
    tenant_a, tenant_b = make_tenant(), make_tenant()
    campaign_a = launch(database_url, tenant_a)

    response = api.get(
        f"/api/v1/campaigns/{campaign_a.id}", headers=auth_headers(tenant_b.owner, tenant_b.organization_id)
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert str(campaign_a.id) not in response.text


def test_member_reads_own_campaign(api, make_tenant, database_url):
    tenant = make_tenant()
    campaign = launch(database_url, tenant)

    response = api.get(f"/api/v1/campaigns/{campaign.id}", headers=auth_headers(tenant.owner, tenant.organization_id))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == str(campaign.id)
    assert data["prospects"] == [] and data["conversation"] is None and data["handoff"] is None
