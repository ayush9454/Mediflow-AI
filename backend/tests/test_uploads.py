"""Upload behavior through authenticated HTTP; platform fakes stay at storage seams."""

from datetime import UTC, datetime
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from mediflow.authorization import Authorization, MemoryIdentityStore
from mediflow.config import Settings
from mediflow.contracts import Account
from mediflow.main import create_app


class Tokens:
    def verify(self, token):
        return token


def laboratory_pdf(label="one"):
    result = BytesIO()
    pdf = canvas.Canvas(result, invariant=True)
    pdf.drawString(40, 750, "Synthetic laboratory report Result Reference interval")
    pdf.drawString(40, 720, "Glucose 92 mg/dL Reference range 70-100 " + label)
    pdf.save()
    return result.getvalue()


@pytest.fixture
def setup_uploads():
    import os

    from mediflow.uploads import MemoryDatabase, MemoryDocuments, Uploads

    database = MemoryDatabase()
    namespace = None
    if os.getenv("MEDIFLOW_UPLOAD_TEST_FIRESTORE") == "1":
        from uuid import uuid4

        from google.auth.credentials import AnonymousCredentials
        from google.cloud import firestore

        from mediflow.uploads.platform import FirestoreDatabase

        assert os.getenv("FIRESTORE_EMULATOR_HOST"), "Real Firestore tests require emulator"
        db = firestore.Client(project="demo-mediflow", credentials=AnonymousCredentials())
        namespace = db.collection("uploadTestRuns").document(uuid4().hex)

        class NamespacedClient:
            def collection(self, name):
                return namespace.collection(name)

            def transaction(self, **kwargs):
                return db.transaction(**kwargs)

        database = FirestoreDatabase(NamespacedClient())
    documents = MemoryDocuments()

    class Identities(MemoryIdentityStore):
        def audit(self, event):
            from dataclasses import asdict
            from uuid import uuid4

            from mediflow.uploads.audit import record_audit

            database.run(lambda tx: record_audit(tx, uuid4().hex, asdict(event), access=True))
            self.events.append(event)

        def report(self, report_id):
            from mediflow.contracts import ReportMetadata

            data = database.run(lambda tx: tx.get("reports", report_id))
            if data:
                case = database.run(lambda tx: tx.get("cases", data["caseId"]))
                if not case or case.get("hospitalId") != data.get("hospitalId"):
                    return None
                data["assignedDoctorId"] = case.get("assignedDoctorId")
                data["caseVersion"] = case.get("version")
            return ReportMetadata.model_validate(data) if data else None

        def case_report_id(self, case_id):
            case = database.run(lambda tx: tx.get("cases", case_id))
            return case.get("reportId") if case else None

    identities = Identities()
    for uid, role in [
        ("patient_a", "patient"),
        ("patient_b", "patient"),
        ("doctor_a", "doctor"),
        ("admin", "administrator"),
    ]:
        identities.accounts[uid] = Account(
            uid=uid, hospital_id="hospital_1", display_name=uid, role=role, active=True
        )
    identities.hospitals.add("hospital_1")

    def seed_accounts(tx):
        tx.put("hospitals", "hospital_1", {"active": True})
        for account in identities.accounts.values():
            tx.put("users", account.uid, account.model_dump(mode="json", by_alias=True))
            if account.role == "doctor":
                tx.put("doctors", account.uid, {"hospitalId": "hospital_1", "active": True})

    database.run(seed_accounts)
    uploads = Uploads(database, documents)
    app = create_app(
        Settings(environment="test"),
        authorization=Authorization(Tokens(), identities),
        uploads=uploads,
    )
    with TestClient(app) as client:
        try:
            yield client, uploads, identities, documents
        finally:
            if namespace is not None:
                db.recursive_delete(namespace)


def headers(uid="patient_a", key="operation_1"):
    return {"Authorization": "Bearer " + uid, "Idempotency-Key": key}


def register(client, source, key="operation_1", uid="patient_a"):
    return client.post(
        "/api/v1/reports",
        headers=headers(uid, key),
        json={
            "fileName": "synthetic.pdf",
            "byteCount": len(source),
            "syntheticDataAcknowledged": True,
        },
    )


def upload(client, session, source, uid="patient_a"):
    return client.put(
        session["uploadPath"],
        headers={**headers(uid), "Content-Type": "application/pdf"},
        content=source,
    )


def complete(client, session, key="complete_1", uid="patient_a"):
    return client.post(
        "/api/v1/reports/" + session["report"]["reportId"] + "/complete-upload",
        headers=headers(uid, key),
        json={},
    )


def test_private_upload_creates_retrievable_report_and_durable_job(setup_uploads):
    client, _, _, _ = setup_uploads
    source = laboratory_pdf()
    registered = register(client, source)
    assert registered.status_code == 201
    session = registered.json()
    assert upload(client, session, source).status_code == 204
    completed = complete(client, session)
    assert completed.status_code == 202
    assert completed.json()["status"] == "queued"
    report_id = completed.json()["reportId"]
    metadata = client.get("/api/v1/reports/" + report_id, headers=headers()).json()
    assert metadata["pageCount"] == 1
    expiry = datetime.fromisoformat(metadata["expiresAt"].replace("Z", "+00:00"))
    assert 29 < (expiry - datetime.now(UTC)).total_seconds() / 86400 <= 30
    document = client.get("/api/v1/reports/" + report_id + "/document", headers=headers())
    assert document.status_code == 200
    assert document.content == source
    assert document.headers["cache-control"] == "no-store"
    assert "blob.core" not in registered.text + completed.text


def test_expired_report_metadata_is_denied_before_cleanup_without_disclosing_filename(
    setup_uploads,
):
    client, uploads, _, _ = setup_uploads
    source = laboratory_pdf()
    session = register(client, source).json()
    assert upload(client, session, source).status_code == 204
    report_id = complete(client, session).json()["reportId"]

    def expire(tx):
        report = tx.get("reports", report_id)
        report["createdAt"] = "2019-12-01T00:00:00+00:00"
        report["expiresAt"] = "2020-01-01T00:00:00+00:00"
        tx.put("reports", report_id, report)

    uploads.database.run(expire)
    response = client.get("/api/v1/reports/" + report_id, headers=headers())
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "expired"
    assert "synthetic.pdf" not in response.text
    assert (
        client.get("/api/v1/reports/" + report_id, headers=headers("patient_b")).status_code == 403
    )


def test_storage_ceiling_is_atomic_and_idempotent_before_any_bytes_are_written(setup_uploads):
    from concurrent.futures import ThreadPoolExecutor

    from mediflow.uploads import Uploads

    client, original, _, documents = setup_uploads
    source = laboratory_pdf()
    client.app.state.uploads = Uploads(
        original.database, documents, storage_limit_bytes=3 * len(source)
    )
    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(lambda key: register(client, source, key), ["first", "second"]))
    assert sorted(response.status_code for response in responses) == [201, 429]
    winner = "first" if responses[0].status_code == 201 else "second"
    assert register(client, source, winner).json() == next(
        response.json() for response in responses if response.status_code == 201
    )
    denied = next(response for response in responses if response.status_code == 429)
    assert denied.json()["error"]["code"] == "quota_exhausted"
    assert "storage" in denied.json()["error"]["message"].lower()
    assert not documents.objects


def test_exhausted_access_audit_budget_fails_closed_without_unbounded_event_growth(setup_uploads):
    client, uploads, _, _ = setup_uploads
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    uploads.database.run(lambda tx: tx.put("auditBudgets", "access-" + day, {"count": 10000}))
    before = uploads.database.page("auditEvents", None, 100)
    for _ in range(3):
        response = client.get("/api/v1/cases", headers=headers())
        assert response.status_code == 429
        assert response.json()["error"]["code"] == "quota_exhausted"
    assert uploads.database.page("auditEvents", None, 100) == before


def test_legacy_payloads_cannot_silently_start_with_an_empty_capacity_ledger(setup_uploads):
    client, uploads, _, _ = setup_uploads
    source = laboratory_pdf()
    assert register(client, source).status_code == 201

    def legacy(tx):
        tx.delete("storagePolicy", "capacity-v1")
        tx.delete("storageCapacity", "hospital_1")

    uploads.database.run(legacy)
    response = register(client, source, key="legacy_restart")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "integration_not_configured"


def test_document_expiring_during_storage_read_is_not_returned(setup_uploads, monkeypatch):
    from datetime import timedelta

    client, uploads, _, documents = setup_uploads
    source = laboratory_pdf()
    session = register(client, source).json()
    assert upload(client, session, source).status_code == 204
    report_id = complete(client, session).json()["reportId"]
    read = documents.read
    started = uploads.clock()

    def delayed_read(key):
        result = read(key)
        uploads.clock = lambda: started + timedelta(days=31)
        return result

    monkeypatch.setattr(documents, "read", delayed_read)
    response = client.get(f"/api/v1/reports/{report_id}/document", headers=headers())
    assert response.status_code == 410
    assert not response.content.startswith(b"%PDF")


def test_registration_and_completion_retries_and_byte_duplicates_reuse_one_case(setup_uploads):
    client, _, _, _ = setup_uploads
    source = laboratory_pdf()
    session = register(client, source).json()
    assert register(client, source).json() == session
    assert upload(client, session, source).status_code == 204
    original = complete(client, session).json()
    assert complete(client, session).json() == original
    assert complete(client, session, key="different_retry").json() == original
    duplicate = register(client, source, key="duplicate").json()
    assert upload(client, duplicate, source).status_code == 204
    assert complete(client, duplicate).json() == original
    retried = register(client, source, key="duplicate").json()
    assert retried["report"]["reportId"] == original["reportId"]
    assert retried["report"]["caseId"] == session["report"]["caseId"]
    # A different patient gets an independent report, even for identical bytes.
    other = register(client, source, uid="patient_b").json()
    assert upload(client, other, source, uid="patient_b").status_code == 204
    assert complete(client, other, uid="patient_b").json()["reportId"] != original["reportId"]


def test_patient_quota_race_and_duplicate_at_limit(setup_uploads):
    from concurrent.futures import ThreadPoolExecutor

    client, _, _, _ = setup_uploads
    first = None
    for number in range(4):
        source = laboratory_pdf(str(number))
        session = register(client, source, key=f"new_{number}").json()
        assert upload(client, session, source).status_code == 204
        response = complete(client, session)
        assert response.status_code == 202
        first = first or (source, response.json())
    pending = []
    for number in range(2):
        source = laboratory_pdf(f"race_{number}")
        session = register(client, source, key=f"race_{number}").json()
        assert upload(client, session, source).status_code == 204
        pending.append(session)
    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(lambda session: complete(client, session), pending))
    assert sorted(response.status_code for response in responses) == [202, 429]
    assert (
        next(r for r in responses if r.status_code == 429).json()["error"]["code"]
        == "quota_exhausted"
    )
    source, original = first
    duplicate = register(client, source, key="duplicate_at_limit").json()
    assert upload(client, duplicate, source).status_code == 204
    assert complete(client, duplicate).json() == original


def test_uploaded_bytes_are_immutable_and_partial_upload_is_retryable(setup_uploads):
    client, _, _, _ = setup_uploads
    source = laboratory_pdf()
    session = register(client, source).json()
    assert upload(client, session, source[:-1]).status_code == 422
    assert complete(client, session).status_code == 409
    assert upload(client, session, source).status_code == 204
    assert upload(client, session, source).status_code == 204
    changed = source.replace(b"%PDF-1.3", b"%PDF-1.4")
    assert changed != source
    assert upload(client, session, changed).status_code == 409
    assert complete(client, session).status_code == 202
    assert upload(client, session, changed).status_code == 409
    assert (
        client.get(
            "/api/v1/reports/" + session["report"]["reportId"] + "/document", headers=headers()
        ).content
        == source
    )


@pytest.mark.parametrize("uid", ["patient_b", "doctor_a", "admin"])
def test_other_accounts_cannot_upload_complete_or_read_private_source(setup_uploads, uid):
    client, _, _, _ = setup_uploads
    source = laboratory_pdf()
    session = register(client, source).json()
    assert upload(client, session, source, uid=uid).status_code == 403
    assert complete(client, session, uid=uid).status_code == 403
    assert upload(client, session, source).status_code == 204
    assert complete(client, session).status_code == 202
    assert (
        client.get(
            "/api/v1/reports/" + session["report"]["reportId"] + "/document", headers=headers(uid)
        ).status_code
        == 403
    )


def test_pending_reservations_and_abandoned_bytes_have_bounded_cleanup(setup_uploads):
    from datetime import timedelta

    client, uploads, _, documents = setup_uploads
    source = laboratory_pdf()
    sessions = [register(client, source, key=f"pending_{i}").json() for i in range(5)]
    assert register(client, source, key="over_reservation_limit").status_code == 429
    assert upload(client, sessions[0], source).status_code == 204
    assert (
        client.get(
            "/api/v1/reports/" + sessions[0]["report"]["reportId"] + "/document", headers=headers()
        ).status_code
        == 409
    )
    current = uploads.clock()
    uploads.clock = lambda: current + timedelta(hours=2)
    assert upload(client, sessions[1], source).status_code == 410
    assert complete(client, sessions[0]).status_code == 410
    assert uploads.cleanup(limit=10) == 5
    assert not documents.objects
    assert register(client, source, key="after_cleanup").status_code == 201


def test_hospital_quota_is_atomic_across_patients(setup_uploads):
    from concurrent.futures import ThreadPoolExecutor

    client, _, identities, _ = setup_uploads
    sessions = []
    for number in range(21):
        uid = f"patient_{number // 5}"
        identities.accounts[uid] = Account(
            uid=uid, hospital_id="hospital_1", display_name=uid, role="patient", active=True
        )
        source = laboratory_pdf(f"hospital_{number}")
        session = register(client, source, key=f"hospital_{number}", uid=uid).json()
        assert upload(client, session, source, uid=uid).status_code == 204
        if number < 19:
            assert complete(client, session, uid=uid).status_code == 202
        else:
            sessions.append((session, uid))
    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(lambda pair: complete(client, pair[0], uid=pair[1]), sessions))
    assert sorted(r.status_code for r in responses) == [202, 429]


@pytest.mark.parametrize("kind", ["forged", "truncated", "encrypted", "over_pages", "unsupported"])
def test_invalid_pdf_inputs_fail_with_safe_stable_errors(setup_uploads, kind):
    from pypdf import PdfReader, PdfWriter

    client, _, _, _ = setup_uploads
    source = laboratory_pdf()
    if kind == "forged":
        source = b"Not a PDF at all"
    elif kind == "truncated":
        source = source[:-100]
    elif kind == "encrypted":
        writer = PdfWriter()
        writer.append(PdfReader(BytesIO(source)))
        writer.encrypt("secret-password")
        output = BytesIO()
        writer.write(output)
        source = output.getvalue()
    elif kind == "over_pages":
        writer = PdfWriter()
        page = PdfReader(BytesIO(source)).pages[0]
        for _ in range(11):
            writer.add_page(page)
        output = BytesIO()
        writer.write(output)
        source = output.getvalue()
    else:
        source = laboratory_pdf("radiology MRI")
    session = register(client, source).json()
    assert upload(client, session, source).status_code == 204
    response = complete(client, session)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_upload"
    assert "secret-password" not in response.text
    metadata = client.get(
        "/api/v1/reports/" + session["report"]["reportId"], headers=headers()
    ).json()
    assert metadata["processingStatus"] == "rejected"
    assert (
        client.get(
            "/api/v1/reports/" + session["report"]["reportId"] + "/document", headers=headers()
        ).status_code
        == 409
    )


def test_actual_stream_size_and_mime_are_enforced_and_acknowledgement_required(setup_uploads):
    client, _, _, _ = setup_uploads
    source = laboratory_pdf()
    session = register(client, source).json()
    assert upload(client, session, source + b"extra").status_code == 413
    assert (
        client.put(
            session["uploadPath"],
            headers={**headers(), "Content-Type": "text/plain"},
            content=source,
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/reports",
            headers=headers(),
            json={"fileName": "s.pdf", "byteCount": 10_000_001, "syntheticDataAcknowledged": True},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/reports",
            headers=headers(),
            json={
                "fileName": "s.pdf",
                "byteCount": len(source),
                "syntheticDataAcknowledged": False,
            },
        ).status_code
        == 422
    )


def test_commit_survives_api_restart_and_duplicate_completion_race(setup_uploads):
    from concurrent.futures import ThreadPoolExecutor

    from mediflow.uploads import Uploads

    client, uploads, identities, documents = setup_uploads
    source = laboratory_pdf()
    sessions = [register(client, source, key=f"same_bytes_{i}").json() for i in range(2)]
    for session in sessions:
        assert upload(client, session, source).status_code == 204
    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(lambda session: complete(client, session), sessions))
    assert [r.status_code for r in responses] == [202, 202]
    assert responses[0].json() == responses[1].json()
    restarted = create_app(
        Settings(environment="test"),
        authorization=Authorization(Tokens(), identities),
        uploads=Uploads(uploads.database, documents),
    )
    with TestClient(restarted) as new_client:
        assert complete(new_client, sessions[0]).json() == responses[0].json()
        assert complete(new_client, sessions[1]).json() == responses[0].json()


def test_uncertain_blob_write_can_be_retried_without_accepting_partial_source(
    setup_uploads, monkeypatch
):
    from mediflow.contracts import ErrorCode
    from mediflow.errors import ApplicationError

    client, _, _, documents = setup_uploads
    source = laboratory_pdf()
    session = register(client, source).json()
    put = documents.put

    def fail_after_write(key, stream, size):
        put(key, stream, size)
        raise ApplicationError(ErrorCode.TEMPORARILY_UNAVAILABLE, 503, "Try again later.")

    monkeypatch.setattr(documents, "put", fail_after_write)
    assert upload(client, session, source).status_code == 503
    assert complete(client, session).status_code == 409
    monkeypatch.setattr(documents, "put", put)
    assert upload(client, session, source).status_code == 204
    assert complete(client, session).status_code == 202


def test_scanned_and_unreadable_pdfs_use_real_bounded_ocr(setup_uploads):
    import shutil

    if shutil.which("tesseract") is None:
        pytest.skip("Run in the Linux test image containing real Tesseract")
    from pathlib import Path

    from PIL import Image, ImageDraw, ImageFont

    client, _, _, _ = setup_uploads
    image = Image.new("RGB", (1200, 1600), "white")
    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    font = next(
        (ImageFont.truetype(path, 28) for path in font_candidates if Path(path).exists()),
        ImageFont.load_default(size=28),
    )
    draw = ImageDraw.Draw(image)
    for i, text in enumerate(
        [
            "Synthetic laboratory report",
            "Analyte Result Unit Reference interval",
            "Glucose 92 mg/dL 70-100",
        ]
    ):
        draw.text((60, 100 + i * 80), text, fill="black", font=font)
    output = BytesIO()
    image.save(output, format="PDF", resolution=150)
    source = output.getvalue()
    session = register(client, source, key="scan").json()
    assert upload(client, session, source).status_code == 204
    assert complete(client, session).status_code == 202
    blank = Image.new("RGB", (1200, 1600), "white")
    output = BytesIO()
    blank.save(output, format="PDF", resolution=150)
    source = output.getvalue()
    session = register(client, source, key="unreadable").json()
    assert upload(client, session, source).status_code == 204
    assert complete(client, session).status_code == 422


def test_maximum_pdf_size_and_page_count_are_accepted(setup_uploads):
    from pypdf import PdfReader, PdfWriter

    client, _, _, _ = setup_uploads
    writer = PdfWriter()
    page = PdfReader(BytesIO(laboratory_pdf())).pages[0]
    for _ in range(10):
        writer.add_page(page)
    output = BytesIO()
    writer.write(output)
    source = output.getvalue()
    # A PDF comment before startxref leaves the existing xref offsets unchanged.
    padding = b"%" + b"A" * (10_000_000 - len(source) - 2) + b"\n"
    source = source.replace(b"startxref", padding + b"startxref", 1)
    assert len(source) == 10_000_000
    session = register(client, source).json()
    assert upload(client, session, source).status_code == 204
    response = complete(client, session)
    assert response.status_code == 202, response.text
    metadata = client.get(
        "/api/v1/reports/" + response.json()["reportId"], headers=headers()
    ).json()
    assert metadata["pageCount"] == 10


def test_database_outage_after_blob_write_does_not_disable_future_uploads(
    setup_uploads, monkeypatch
):
    from mediflow.contracts import ErrorCode
    from mediflow.errors import ApplicationError

    client, uploads, _, documents = setup_uploads
    source = laboratory_pdf()
    interrupted = register(client, source, key="interrupted").json()
    other = register(client, source, key="after_recovery").json()
    available = True
    run = uploads.database.run
    put = documents.put

    def database_run(operation):
        if not available:
            raise ApplicationError(ErrorCode.TEMPORARILY_UNAVAILABLE, 503, "Try again later.")
        return run(operation)

    def write_then_database_outage(key, stream, size):
        nonlocal available
        put(key, stream, size)
        available = False

    monkeypatch.setattr(uploads.database, "run", database_run)
    monkeypatch.setattr(documents, "put", write_then_database_outage)
    assert upload(client, interrupted, source).status_code == 503
    available = True
    monkeypatch.setattr(documents, "put", put)
    assert upload(client, other, source).status_code == 204
    assert complete(client, other).status_code == 202


def test_late_writer_after_takeover_and_cleanup_is_eventually_removed(setup_uploads, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import timedelta
    from threading import Event

    from mediflow.uploads import Uploads

    client, uploads, identities, documents = setup_uploads
    source = laboratory_pdf()
    session = register(client, source).json()
    entered = Event()
    resume = Event()
    put = documents.put

    def delayed_first_put(key, stream, size):
        if not entered.is_set():
            entered.set()
            assert resume.wait(20), "Test did not release delayed storage write"
        put(key, stream, size)

    monkeypatch.setattr(documents, "put", delayed_first_put)
    current = uploads.clock()
    replacement = Uploads(uploads.database, documents, clock=lambda: current + timedelta(minutes=7))
    new_app = create_app(
        Settings(environment="test"),
        authorization=Authorization(Tokens(), identities),
        uploads=replacement,
    )
    with ThreadPoolExecutor(1) as pool, TestClient(new_app) as new_client:
        old = pool.submit(upload, client, session, source)
        try:
            assert entered.wait(5)
            assert upload(new_client, session, source).status_code == 204
            replacement.clock = lambda: current + timedelta(hours=2)
            assert replacement.cleanup() == 1
        finally:
            resume.set()
        assert old.result(timeout=10).status_code == 409
    # A durable prefix sweep catches a write arriving after reservation removal.
    replacement.clock = lambda: current + timedelta(days=1, hours=2)
    replacement.cleanup()
    assert documents.objects == {}
