import click
from flask.cli import with_appcontext

from .extensions import db


def register_cli(app):
    @app.cli.command("seed")
    @click.option("--no-reset", is_flag=True, help="Append instead of dropping and recreating tables.")
    @with_appcontext
    def seed_cmd(no_reset):
        """Drop all tables, recreate them and load the synthetic data set."""
        from .seed import run
        run(reset=not no_reset)
        if not no_reset:
            # keep alembic in step with the freshly created schema
            from flask_migrate import stamp
            try:
                stamp()
            except Exception as e:  # migrations folder missing in some setups
                click.echo(f"(alembic stamp skipped: {e})")
        click.echo("Seeded synthetic data.")

    @app.cli.command("refresh-prices")
    @with_appcontext
    def refresh_cmd():
        """Run one simulated price tick (use a real feed in production)."""
        from .services.portfolio import refresh_prices
        refresh_prices()
        db.session.commit()
        click.echo("Prices refreshed.")

    @app.cli.command("create-user")
    @click.argument("username")
    @click.argument("name")
    @click.option("--role", default="analyst")
    @click.option("--password", prompt=True, hide_input=True)
    @with_appcontext
    def create_user(username, name, role, password):
        from .models import User
        u = User(username=username, name=name, email=f"{username}@example.com", role=role)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        click.echo(f"Created {username} ({role}).")


    @app.cli.command("rotate-passwords")
    @click.option("--out", required=True, type=click.Path(), help="File to write the new passwords to (mode 600). Passwords are never printed.")
    @with_appcontext
    def rotate_passwords(out):
        """Give every user a fresh random password, e.g. before a public deploy."""
        import os
        import secrets
        from .models import User
        lines = []
        for u in User.query.order_by(User.id).all():
            pw = secrets.token_urlsafe(18)
            u.set_password(pw)
            lines.append(f"{u.username}\t{u.role}\t{pw}")
        db.session.commit()
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write("# username\trole\tpassword\n" + "\n".join(lines) + "\n")
        os.chmod(out, 0o600)
        click.echo(f"Rotated {len(lines)} passwords; written to {out}.")
