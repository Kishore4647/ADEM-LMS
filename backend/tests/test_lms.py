from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.routes.auth import get_current_user
from app.core.database import Base, get_db
from app.main import app
from app.models import (
    CurriculumBoard,
    CurriculumLevel,
    CurriculumNode,
    School,
    StudentProfile,
    User,
    UserRole,
    UserSchoolAssignment,
)
from app.models.workflows import QuestionSet, TeachingAssignment
from app.services.docx_import import import_docx
from app.services.grading import component_score


@pytest.fixture
def env(tmp_path, monkeypatch):
    import app.api.routes.imports as import_routes
    import app.api.routes.workflows as workflow_routes

    monkeypatch.setattr(workflow_routes, "STORAGE", tmp_path)
    monkeypatch.setattr(import_routes, "STORAGE", tmp_path)
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        users = [
            User(
                email=f"{r.value}@example.com",
                google_subject=r.value,
                role=r,
                full_name=r.value,
            )
            for r in UserRole
        ]
        db.add_all(users)
        db.flush()
        accounts = {u.role.value: u.id for u in users}
        a = School(name="A School", code="A")
        b = School(name="B School", code="B")
        board = CurriculumBoard(name="Board")
        db.add_all([a, b, board])
        db.flush()
        nodes = []
        parent = None
        for level in CurriculumLevel:
            node = CurriculumNode(
                name=level.value, level=level, board_id=board.id, parent_id=parent
            )
            db.add(node)
            db.flush()
            nodes.append(node.id)
            parent = node.id
        for u in users:
            db.add(UserSchoolAssignment(user_id=u.id, school_id=a.id))
        student = StudentProfile(
            user_id=accounts["student"], school_id=a.id, class_node_id=nodes[0]
        )
        db.add(student)
        db.flush()
        db.add(
            TeachingAssignment(
                user_id=accounts["ist"], school_id=a.id, subject_id=nodes[1]
            )
        )
        db.commit()
        ids = dict(
            accounts=accounts,
            school=a.id,
            other_school=b.id,
            nodes=nodes,
            student=student.id,
        )
    actor = {"id": accounts["super_admin"]}

    def database():
        with Session(engine) as db:
            yield db

    def identity():
        with Session(engine) as db:
            return db.get(User, actor["id"])

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = identity
    client = TestClient(app, headers={"Origin": "http://localhost:5173"})
    yield client, actor, ids, engine
    app.dependency_overrides.clear()
    engine.dispose()


def mark_payload(ids, **changes):
    return dict(
        student_id=ids["student"],
        subject_node_id=ids["nodes"][1],
        component="assessment",
        academic_period="2026-Q1",
        title="Test",
        obtained_marks=8,
        maximum_marks=10,
        is_absent=False,
        **changes,
    )


def test_rounding_and_absence_exclusion():
    records = [
        SimpleNamespace(obtained_marks=8, maximum_marks=10, is_absent=False),
        SimpleNamespace(obtained_marks=None, maximum_marks=20, is_absent=True),
    ]
    assert component_score(records, "exclude") == 8.0
    assert component_score(records, None) is None
    assert (
        component_score(
            [SimpleNamespace(obtained_marks=1, maximum_marks=6, is_absent=False)],
            "exclude",
        )
        == 1.67
    )
    assert component_score([records[1]], "exclude") is None


def test_cross_school_and_role_boundaries(env):
    client, actor, ids, _ = env
    actor["id"] = ids["accounts"]["ist"]
    assert (
        client.post(
            "/api/admin/schools", json={"name": "Denied", "code": "D"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/workspace/assets",
            json=dict(
                school_id=ids["other_school"],
                subtopic_id=ids["nodes"][-1],
                title="Denied",
                drive_url="https://drive.google.com/file/d/abc/view",
            ),
        ).status_code
        == 403
    )
    assert client.get("/api/workspace/audit").status_code == 403
    actor["id"] = ids["accounts"]["student"]
    assert (
        client.post("/api/workspace/marks", json=mark_payload(ids)).status_code == 403
    )
    assert client.get("/api/workspace/question-sets/999").status_code == 403


def test_marks_attendance_review_and_progress(env):
    client, actor, ids, engine = env
    actor["id"] = ids["accounts"]["ist"]
    created = client.post(
        "/api/workspace/sessions",
        json=dict(
            school_id=ids["school"],
            subject_id=ids["nodes"][1],
            session_date="2026-10-26",
            period="2026-Q1",
            subtopic_ids=[ids["nodes"][-1]],
            notes="Coverage",
        ),
    )
    assert created.status_code == 200, created.text
    session = created.json()["id"]
    payload = mark_payload(ids)
    payload.update(
        obtained_marks=0, maximum_marks=20, session_id=session, manual_present=False
    )
    saved = client.post("/api/workspace/marks", json=payload)
    assert saved.status_code == 200, saved.text
    mark_id = saved.json()["id"]
    assert (
        client.get("/api/workspace/data").json()["attendance"][0]["final_status"]
        == "Present"
    )
    payload.update(obtained_marks=None, is_absent=True, manual_present=True)
    assert (
        client.put(f"/api/workspace/marks/{mark_id}", json=payload).status_code == 200
    )
    assert (
        client.get("/api/workspace/data").json()["attendance"][0]["final_status"]
        == "Absent"
    )
    assert (
        client.post(f"/api/workspace/sessions/{session}/submit", json={}).status_code
        == 200
    )
    actor["id"] = ids["accounts"]["super_admin"]
    assert (
        client.post(
            f"/api/workspace/sessions/{session}/review",
            json={"status": "rejected", "comment": ""},
        ).status_code
        == 400
    )
    assert (
        client.post(
            f"/api/workspace/sessions/{session}/review",
            json={"status": "rejected", "comment": "Correct coverage"},
        ).status_code
        == 200
    )
    actor["id"] = ids["accounts"]["ist"]
    assert (
        client.patch(
            f"/api/workspace/sessions/{session}", json={"notes": "Corrected"}
        ).status_code
        == 200
    )
    assert (
        client.post(f"/api/workspace/sessions/{session}/submit", json={}).status_code
        == 200
    )
    for component, obtained, maximum in [
        ("assessment", 15, 20),
        ("activity", 4, 5),
        ("quarterly_exam", 72, 80),
    ]:
        payload = mark_payload(ids)
        payload.update(
            component=component, obtained_marks=obtained, maximum_marks=maximum
        )
        response = client.post("/api/workspace/marks", json=payload)
        assert response.status_code == 200, response.text
    query = f"student_id={ids['student']}&subject_id={ids['nodes'][1]}&period=2026-Q1"
    result = client.get("/api/workspace/results?" + query).json()
    assert result["total"] == 87.5, result
    actor["id"] = ids["accounts"]["super_admin"]
    publication = client.post(
        "/api/workspace/progress/publish",
        json=dict(
            student_id=ids["student"], subject_id=ids["nodes"][1], period="2026-Q1"
        ),
    )
    assert publication.status_code == 200, publication.text
    pdf = client.get(f"/api/workspace/progress/{publication.json()['id']}/pdf")
    assert pdf.content.startswith(b"%PDF")
    actor["id"] = ids["accounts"]["student"]
    assert client.get("/api/workspace/data").json()["users"] == []
    actor["id"] = ids["accounts"]["ist"]
    correction = mark_payload(ids)
    correction.update(
        obtained_marks=0, maximum_marks=20, session_id=session, manual_present=True
    )
    assert (
        client.put(f"/api/workspace/marks/{mark_id}", json=correction).status_code
        == 200
    )
    actor["id"] = ids["accounts"]["student"]
    assert (
        client.get(
            f"/api/workspace/progress/{publication.json()['id']}/pdf"
        ).status_code
        == 409
    )


def test_mcq_dispatch_attempts_and_answer_privacy(env):
    client, actor, ids, engine = env
    with Session(engine) as db:
        question = dict(
            prompt="<p>2+2?</p>",
            options=["1", "2", "3", "4"],
            correct=3,
            hint="Add",
            explanation="Four",
        )
        q = QuestionSet(
            school_id=ids["school"],
            subtopic_id=ids["nodes"][-1],
            title="Imported test",
            difficulty="easy",
            questions=[question],
            created_by=actor["id"],
            policy=dict(
                correct_marks=2,
                incorrect_penalty=0.5,
                max_attempts=2,
                counted_attempt="best",
            ),
        )
        db.add(q)
        db.commit()
        qid = q.id
    actor["id"] = ids["accounts"]["content_uploader"]
    assert (
        client.post(f"/api/workspace/question-sets/{qid}/dispatch", json={}).status_code
        == 200
    )
    assert (
        client.post(f"/api/workspace/question-sets/{qid}/dispatch", json={}).status_code
        == 200
    )
    actor["id"] = ids["accounts"]["student"]
    data = client.get("/api/workspace/data").json()
    assert len(data["assignments"]) == 1
    assert "questions" not in data["question_sets"][0]
    aid = data["assignments"][0]["id"]
    preview = client.get(f"/api/workspace/attempts/{aid}").json()
    assert (
        "correct" not in preview["questions"][0]
        and "explanation" not in preview["questions"][0]
    )
    wrong = client.post(f"/api/workspace/attempts/{aid}/submit", json={"answers": [0]})
    assert wrong.json()["score"] == -0.5
    right = client.post(f"/api/workspace/attempts/{aid}/submit", json={"answers": [3]})
    assert right.json()["counted_score"] == 2
    assert (
        client.post(
            f"/api/workspace/attempts/{aid}/submit", json={"answers": [3]}
        ).status_code
        == 409
    )
    assert client.get("/api/workspace/data").json()["marks"] == []

    correction = {"attempt_number": 2, "score": 1, "reason": "Answer-key review"}
    actor["id"] = ids["accounts"]["ist"]
    assert (
        client.post(
            f"/api/workspace/attempts/{aid}/correct", json=correction
        ).status_code
        == 403
    )
    actor["id"] = ids["accounts"]["super_admin"]
    corrected = client.post(f"/api/workspace/attempts/{aid}/correct", json=correction)
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["counted_score"] == 1
    actor["id"] = ids["accounts"]["student"]
    after = client.get(f"/api/workspace/attempts/{aid}").json()
    assert after["history"][1]["original_score"] == 2
    assert after["history"][1]["score"] == 1


def test_source_documents_strict_format():
    root = Path(__file__).resolve().parents[2] / "MCQ" / "MCQ"
    passed = 0
    errors = {}
    for path in root.rglob("*.docx"):
        if path.stem[-2:] not in {"_e", "_m", "_h"}:
            continue
        try:
            result = import_docx(path.read_bytes())
            assert result["questions"]
            passed += 1
        except ValueError as error:
            errors[path.name] = str(error)
    assert passed == 13
    assert "Question 5" in errors["NC080501_e.docx"]
    assert "Question 3" in errors["NC080501_m.docx"]


def test_csrf_origin_rejected(env):
    client, _, _, _ = env
    assert (
        client.post(
            "/api/admin/schools",
            json={"name": "Bad", "code": "B"},
            headers={"Origin": "https://untrusted.example"},
        ).status_code
        == 403
    )


def test_real_word_upload_review_dispatch_and_file_access(env):
    client, actor, ids, _ = env
    actor["id"] = ids["accounts"]["content_uploader"]
    source = (
        Path(__file__).resolve().parents[2]
        / "MCQ"
        / "MCQ"
        / "Maths"
        / "NNM070203_e.docx"
    )
    uploaded = client.post(
        "/api/workspace/files",
        files={
            "file": (
                source.name,
                source.read_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert uploaded.status_code == 200, uploaded.text
    fid = uploaded.json()["id"]
    imported = client.post(
        "/api/workspace/question-sets/import",
        data=dict(
            file_id=fid,
            school_id=ids["school"],
            subtopic_id=ids["nodes"][-1],
            difficulty="easy",
        ),
    )
    assert imported.status_code == 200, imported.text
    qid = imported.json()["id"]
    assert len(imported.json()["questions"]) == 6
    assert (
        client.post(f"/api/workspace/question-sets/{qid}/dispatch", json={}).status_code
        == 400
    )
    questions = client.get(f"/api/workspace/question-sets/{qid}").json()["questions"]
    edited = client.put(
        f"/api/workspace/question-sets/{qid}",
        json=dict(
            title="Reviewed mathematics",
            questions=questions,
            category="practice",
            policy=dict(
                correct_marks=2,
                incorrect_penalty=0,
                max_attempts=1,
                counted_attempt="latest",
            ),
        ),
    )
    assert edited.status_code == 200, edited.text
    assert (
        client.post(f"/api/workspace/question-sets/{qid}/dispatch", json={}).status_code
        == 200
    )
    assert client.get(f"/api/workspace/files/{fid}").content == source.read_bytes()
    actor["id"] = ids["accounts"]["student"]
    assert client.get(f"/api/workspace/files/{fid}").status_code == 403
    assert client.get(f"/api/workspace/question-sets/{qid}").status_code == 403


def test_marks_import_preview_commit_and_idempotency(env):
    client, actor, ids, _ = env
    actor["id"] = ids["accounts"]["content_uploader"]
    csv = f"student_email,subject_id,component,academic_period,title,marks,maximum,absent\nstudent@example.com,{ids['nodes'][1]},quarterly_exam,2026-Q1,Term exam,70,80,false\nunknown@example.com,{ids['nodes'][1]},quarterly_exam,2026-Q1,Term exam,70,80,false\n"
    uploaded = client.post(
        "/api/workspace/files", files={"file": ("marks.csv", csv.encode(), "text/csv")}
    )
    preview = client.post(
        "/api/workspace/imports/preview", json={"file_id": uploaded.json()["id"]}
    )
    assert preview.status_code == 200, preview.text
    job = preview.json()
    assert job["summary"] == dict(valid=1, invalid=1)
    committed = client.post(f"/api/workspace/imports/{job['id']}/commit", json={})
    assert committed.status_code == 200, committed.text
    assert committed.json()["summary"] == dict(successful=1, failed=0, skipped=1)
    assert (
        client.post(f"/api/workspace/imports/{job['id']}/commit", json={}).status_code
        == 409
    )
    assert len(client.get("/api/workspace/data").json()["marks"]) == 1


def test_unauthenticated_requests_and_public_hall(env):
    client, _, _, _ = env
    saved = app.dependency_overrides.pop(get_current_user)
    try:
        assert client.get("/api/workspace/data").status_code == 401
        assert client.get("/api/public/hall-of-fame").json() == []
    finally:
        app.dependency_overrides[get_current_user] = saved


def test_media_readiness_and_disabled_school_scope(env):
    client, actor, ids, _ = env
    actor["id"] = ids["accounts"]["content_uploader"]
    asset = client.post(
        "/api/workspace/assets",
        json=dict(
            school_id=ids["school"],
            subtopic_id=ids["nodes"][-1],
            title="Video",
            drive_url="https://drive.google.com/file/d/example/view",
            published=True,
        ),
    )
    assert asset.status_code == 200, asset.text
    aid = asset.json()["id"]
    actor["id"] = ids["accounts"]["ist"]
    assert (
        client.post(
            f"/api/workspace/assets/{aid}/ready", json={"ready": True}
        ).status_code
        == 200
    )
    assert client.get("/api/workspace/data").json()["assets"][0]["ready_by"] == [
        actor["id"]
    ]
    actor["id"] = ids["accounts"]["super_admin"]
    assert (
        client.patch(
            f"/api/workspace/schools/{ids['school']}", json={"is_active": False}
        ).status_code
        == 200
    )
    actor["id"] = ids["accounts"]["ist"]
    data = client.get("/api/workspace/data").json()
    assert data["schools"] == [] and data["students"] == [] and data["assets"] == []


def test_class_marks_are_atomic_and_repeat_saves_update_records(env):
    client, actor, ids, _ = env
    actor["id"] = ids["accounts"]["ist"]
    valid = mark_payload(ids)
    invalid = {**valid, "student_id": 999}
    failed = client.post("/api/workspace/marks/batch", json={"marks": [valid, invalid]})
    assert failed.status_code == 404, failed.text
    assert client.get("/api/workspace/data").json()["marks"] == []
    first = client.post("/api/workspace/marks/batch", json={"marks": [valid]})
    assert first.status_code == 200, first.text
    corrected = client.post(
        "/api/workspace/marks/batch", json={"marks": [{**valid, "obtained_marks": 9}]}
    )
    assert corrected.status_code == 200, corrected.text
    marks = client.get("/api/workspace/data").json()["marks"]
    assert len(marks) == 1 and marks[0]["obtained_marks"] == 9


def test_corrupt_uploads_are_rejected_before_storage(env):
    client, actor, ids, _ = env
    actor["id"] = ids["accounts"]["content_uploader"]
    for name, data in [
        ("bad.docx", b"PKbroken"),
        ("bad.png", b"\x89PNG\r\n\x1a\nbroken"),
        ("empty.csv", b""),
    ]:
        assert (
            client.post(
                "/api/workspace/files",
                files={"file": (name, data, "application/octet-stream")},
            ).status_code
            == 400
        )


def test_rich_word_equation_table_and_image_import():
    import io
    from zipfile import ZipFile

    from PIL import Image

    def paragraph(text):
        return "<w:p><w:r><w:t>" + text + "</w:t></w:r></w:p>"

    metadata = "".join(
        paragraph(text)
        for text in [
            "[Lesson] Fractions",
            "[Sub-Topic] Evaluate",
            "[Type]0",
            "[Marks]1",
            "[Negative Marks]0",
        ]
    )
    prompt = '<w:p><w:r><w:t>Q.1) Evaluate </w:t></w:r><m:oMath><m:f><m:num><m:r><m:t>1</m:t></m:r></m:num><m:den><m:r><m:t>2</m:t></m:r></m:den></m:f></m:oMath><w:r><w:drawing><a:blip r:embed="rId1"/></w:drawing></w:r></w:p>'
    table = (
        "<w:tbl><w:tr><w:tc>" + paragraph("Diagram context") + "</w:tc></w:tr></w:tbl>"
    )
    options = "".join(
        paragraph(text)
        for text in [
            "[a] a) 0",
            "*[b] b) 0.5",
            "[c] c) 1",
            "[d] d) 2",
            "[S1] One half equals 0.5.",
            "[Hint] Divide numerator by denominator.",
        ]
    )
    xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body>'
        + metadata
        + prompt
        + table
        + options
        + "</w:body></w:document>"
    )
    image = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(image, format="PNG")
    output = io.BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", xml)
        archive.writestr(
            "word/_rels/document.xml.rels",
            '<Relationships><Relationship Id="rId1" Target="media/image.png"/></Relationships>',
        )
        archive.writestr("word/media/image.png", image.getvalue())
    question = import_docx(output.getvalue())["questions"][0]
    assert "<mfrac>" in question["prompt"]
    assert "<table>" in question["prompt"]
    assert "data:image/png;base64," in question["prompt"]
    assert question["correct"] == 1


def test_curriculum_and_school_edits_preserve_identity_and_require_permissions(env):
    client, actor, ids, _ = env
    subject = ids["nodes"][1]
    changed = client.patch(
        f"/api/curriculum/nodes/{subject}", json={"name": "Mathematics", "sequence": 2}
    )
    assert changed.status_code == 200, changed.text
    assert (
        changed.json()["parent_id"] == ids["nodes"][0]
        and changed.json()["id"] == subject
    )
    assert (
        client.patch(
            f"/api/curriculum/nodes/{subject}",
            json={"name": "Moved", "sequence": 1, "parent_id": 999},
        ).status_code
        == 422
    )
    school = client.put(
        f"/api/workspace/schools/{ids['school']}",
        json={"name": "Renamed School", "code": "NEW", "address": "School address"},
    )
    assert school.status_code == 200, school.text
    actor["id"] = ids["accounts"]["school_management"]
    assert (
        client.patch(
            f"/api/curriculum/nodes/{subject}", json={"name": "Denied", "sequence": 1}
        ).status_code
        == 403
    )


def test_public_hall_displays_only_explicitly_authorised_fields(env):
    client, actor, ids, _ = env
    settings = dict(
        ranking="average_percentage",
        week_starts=0,
        timezone="Asia/Kolkata",
        hall_student_ids=[ids["student"]],
        public_display_authorised=False,
    )
    assert (
        client.put("/api/workspace/community/settings", json=settings).status_code
        == 400
    )
    settings["public_display_authorised"] = True
    assert (
        client.put("/api/workspace/community/settings", json=settings).status_code
        == 200
    )
    response = client.get("/api/public/hall-of-fame")
    assert response.status_code == 200 and len(response.json()) == 1
    assert set(response.json()[0]) == {"name", "class_name"}
    actor["id"] = ids["accounts"]["student"]
    assert (
        client.put("/api/workspace/community/settings", json=settings).status_code
        == 403
    )
