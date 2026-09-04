# plotspace/tests/test_upload_rel_paths.py
"""Fase 7 — POST /files/upload con rel_paths preserva subdirectorios."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from plotspace.tests._harness import fresh_db, make_client_and_project


def test_rel_paths_preserva_subdirs():
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)

    r = client.post(
        f"/api/projects/{pid}/files/upload",
        files=[
            ("files", ("main.py", b"print('hi')", "text/plain")),
            ("files", ("util.py", b"x = 1", "text/plain")),
        ],
        data={"rel_paths": ["src/main.py", "src/lib/util.py"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert sorted(body["subidos"]) == ["src/lib/util.py", "src/main.py"], body
    assert body["rechazados"] == [], body

    # Estructura real en disco
    assert os.path.isfile(os.path.join(d, "src", "main.py"))
    assert os.path.isfile(os.path.join(d, "src", "lib", "util.py"))
    with open(os.path.join(d, "src", "main.py"), encoding="utf-8") as f:
        assert f.read() == "print('hi')"


def test_sin_rel_paths_cae_a_basename():
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)

    r = client.post(
        f"/api/projects/{pid}/files/upload",
        files=[("files", ("solo.txt", b"abc", "text/plain"))],
    )
    assert r.status_code == 200, r.text
    assert r.json()["subidos"] == ["solo.txt"], r.text
    assert os.path.isfile(os.path.join(d, "solo.txt"))


if __name__ == "__main__":
    test_rel_paths_preserva_subdirs()
    test_sin_rel_paths_cae_a_basename()
    print("OK")
