"""/login era el canje del token. Ya no hay token: redirige al home."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi.testclient import TestClient

from plotspace.tests._harness import fresh_db


def test_login_redirige_al_home():
    fresh_db()
    import plotspace.main as main
    client = TestClient(main.app)
    r = client.get('/login', follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get('location') == '/'
    r2 = client.get('/login?token=lo-que-sea', follow_redirects=False)
    assert r2.status_code == 302
    assert r2.headers.get('location') == '/'


if __name__ == '__main__':
    test_login_redirige_al_home()
    print('ok  test_login_redirige_al_home')
