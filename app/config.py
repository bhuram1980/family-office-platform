import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-me")
    if os.environ.get("VERCEL") and SECRET_KEY == "dev-change-me":
        raise RuntimeError("SECRET_KEY must be set in production")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://postgres@localhost:5432/fo"
    ).replace("postgres://", "postgresql+psycopg://", 1).replace("postgresql://", "postgresql+psycopg://", 1)
    ON_VERCEL = bool(os.environ.get("VERCEL"))
    # Serverless: keep few connections per instance, recycle them, and skip server-side
    # prepared statements so the Neon/PgBouncer pooled endpoint is safe.
    SQLALCHEMY_ENGINE_OPTIONS = (
        {"pool_pre_ping": True, "pool_size": 2, "max_overflow": 3, "pool_recycle": 280, "connect_args": {"prepare_threshold": None}}
        if ON_VERCEL else {"pool_pre_ping": True}
    )
    SESSION_COOKIE_SECURE = ON_VERCEL or os.environ.get("SESSION_COOKIE_SECURE") == "1"
    BRAND = os.environ.get("BRAND", "Alladin Family Office")
    MAX_CONTENT_LENGTH = (4 if os.environ.get("VERCEL") else 15) * 1024 * 1024  # Vercel caps request bodies at 4.5 MB
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 12
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    WTF_CSRF = True


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "TEST_DATABASE_URL", "postgresql+psycopg://postgres@localhost:5432/fo_test"
    )
