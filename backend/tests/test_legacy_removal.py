import pytest
from abacus.schemas import AdvisorIn, SavingsProjectionIn, SettingsIn
from pydantic import ValidationError


@pytest.mark.parametrize(
    "path", ["/api/purchases", "/api/bill-estimates", "/api/reserve-check"]
)
def test_retired_routes_are_absent(client, path):
    assert client.get(path).status_code == 404
    assert client.post(path, json={}).status_code == 404


@pytest.mark.parametrize("field", ["purchase_id", "bill_estimate_id"])
def test_advisor_rejects_retired_inputs(field):
    with pytest.raises(ValidationError):
        AdvisorIn(month="2026-11", message="Budget check", **{field: "old"})


def test_rejects_old_projection_and_reserve_preferences():
    with pytest.raises(ValidationError):
        SavingsProjectionIn(start_month="2026-11", estimate_id="old")
    with pytest.raises(ValidationError):
        SettingsIn(
            currency="USD", model="", advisor_enabled=False, reserve_alerts_enabled=True
        )
