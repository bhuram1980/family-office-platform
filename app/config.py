import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://postgres@localhost:5432/fo"
    ).replace("postgres://", "postgresql+psycopg://", 1).replace("postgresql://", "postgresql+psycopg://", 1)
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    BRAND = os.environ.get("BRAND", "Bhuram Family Office")
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 12
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    WTF_CSRF = True


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "TEST_DATABASE_URL", "postgresql+psycopg://postgres@localhost:5432/fo_test"
    )
