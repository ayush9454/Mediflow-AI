"""Patient workflow metadata through the authenticated HTTP boundary."""

import pytest
from test_uploads import headers, laboratory_pdf, register, setup_uploads  # noqa: F401


@pytest.fixture(name="patient_setup")
def patient_setup_fixture(request):
    return request.getfixturevalue("setup_uploads")


def test_case_list_is_patient_scoped_paginated_and_contains_no_clinical_payload(patient_setup):
    client, _, _, _ = patient_setup
    first = register(client, laboratory_pdf(), key="first").json()["report"]
    second = register(client, laboratory_pdf(), key="second").json()["report"]
    other = register(client, laboratory_pdf(), key="other", uid="patient_b").json()["report"]
    response = client.get("/api/v1/cases?limit=1", headers=headers())
    assert response.status_code == 200
    page = response.json()
    assert len(page["items"]) == 1 and page["nextCursor"]
    following = client.get(
        "/api/v1/cases", params={"limit": 1, "cursor": page["nextCursor"]}, headers=headers()
    ).json()
    assert {page["items"][0]["reportId"], following["items"][0]["reportId"]} == {
        first["reportId"],
        second["reportId"],
    }
    assert following["nextCursor"] is None
    assert other["reportId"] not in response.text
    assert not {"rows", "summary", "quotation", "objectKey", "fileName"} & page["items"][0].keys()


def test_cursors_cannot_cross_accounts_and_malformed_cursors_are_safe(patient_setup):
    client, _, _, _ = patient_setup
    for key in ("one", "two"):
        register(client, laboratory_pdf(), key=key)
    cursor = client.get("/api/v1/cases?limit=1", headers=headers()).json()["nextCursor"]
    for token in (cursor, "not-a-cursor"):
        response = client.get(
            "/api/v1/cases", params={"cursor": token}, headers=headers("patient_b")
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_request"


@pytest.mark.parametrize("uid", ["doctor_a", "admin"])
def test_patient_case_endpoint_does_not_enable_later_role_workflows(patient_setup, uid):
    client, _, _, _ = patient_setup
    assert client.get("/api/v1/cases", headers=headers(uid)).status_code == 403


def test_list_includes_expiry_for_patient_status_without_content(patient_setup):
    from test_uploads import complete, upload

    client, _, _, _ = patient_setup
    source = laboratory_pdf()
    session = register(client, source).json()
    assert upload(client, session, source).status_code == 204
    assert complete(client, session).status_code == 202
    item = client.get("/api/v1/cases", headers=headers()).json()["items"][0]
    assert item["expiresAt"]


def test_old_authorization_fixture_is_not_presented_as_a_real_processing_case(patient_setup):
    client, uploads, _, _ = patient_setup
    record = register(client, laboratory_pdf()).json()["report"]
    # Ticket-04 seed used this deliberately incomplete shape for authorization checks.
    uploads.database.run(
        lambda tx: tx.put(
            "cases",
            record["caseId"],
            {
                "reportId": record["reportId"],
                "patientId": "patient_a",
                "hospitalId": "hospital_1",
                "assignedDoctorId": "doctor_a",
                "version": 1,
            },
        )
    )
    response = client.get("/api/v1/cases", headers=headers())
    assert response.status_code == 200
    assert response.json()["items"] == []
