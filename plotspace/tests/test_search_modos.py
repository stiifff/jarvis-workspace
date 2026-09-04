"""Test: GET /files/search — flags case_sensitive, whole_word y regex."""
import os
import sys
import tempfile

# Asegurar imports absolutos 'plotspace.*' al correr el test como script suelto.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from plotspace.tests._harness import fresh_db, make_client_and_project


def main():
    fresh_db()
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "f.txt"), "w", encoding="utf-8") as f:
        f.write("Foo y foo y FooBar\nfoobar suelto\nnum 42 y 420\n")

    client, pid = make_client_and_project(d)

    def search(**params):
        r = client.get(f"/api/projects/{pid}/files/search", params=params)
        assert r.status_code == 200, f"{r.status_code}: {r.text}"
        return r.json()

    # case_sensitive=False (default): 'foo' matchea Foo, foo, FooBar, foobar
    d1 = search(q="foo")
    assert d1["total"] == 4, d1

    # case_sensitive=True: solo 'foo' literal minúscula (en 'foo' linea1 y 'foobar' linea2)
    d2 = search(q="foo", case_sensitive=True)
    assert d2["total"] == 2, d2

    # whole_word: 'foo' como palabra completa (no FooBar/foobar). case-insensitive → Foo, foo = 2
    d3 = search(q="foo", whole_word=True)
    assert d3["total"] == 2, d3

    # regex: \d{3} matchea '420' (3 dígitos), no '42'
    d4 = search(q=r"\d{3}", regex=True)
    assert d4["total"] == 1, d4
    m = d4["results"][0]["matches"][0]
    assert m["length"] == 3 and m["text"].strip().startswith("num"), m

    print("OK")


if __name__ == "__main__":
    main()
