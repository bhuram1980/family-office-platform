def test_setup_route_absent_without_token(app):
    assert not [r for r in app.url_map.iter_rules() if r.rule == "/_setup"]


def test_rotate_passwords_writes_private_file(app, tmp_path):
    import os
    from app.models import User
    out = tmp_path / "creds"
    r = app.test_cli_runner().invoke(args=["rotate-passwords", "--out", str(out)])
    assert r.exit_code == 0 and "bhuram" not in r.output
    assert oct(os.stat(out).st_mode & 0o777) == "0o600"
    user, _, pw = out.read_text().splitlines()[1].split("\t")
    assert pw not in r.output and len(pw) >= 20
    assert User.query.filter_by(username=user).one().check_password(pw)
    # restore the shared test password for the other tests
    for u in User.query.all():
        u.set_password("bhuram-demo")
    from app.extensions import db
    db.session.commit()
