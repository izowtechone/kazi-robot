"""initial schema"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None

def upgrade():
    op.create_table("users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("full_name", sa.String(255)),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="viewer"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_table("sources",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("country", sa.String(40)),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("reliability", sa.Integer, nullable=False, server_default="80"),
        sa.Column("interval_minutes", sa.Integer),
        sa.Column("config", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("last_status", sa.String(40)),
        sa.Column("last_message", sa.Text),
        sa.Column("consecutive_failures", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_table("jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source_id", sa.Integer, sa.ForeignKey("sources.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("employer", sa.String(500)),
        sa.Column("country", sa.String(40)),
        sa.Column("location", sa.String(255)),
        sa.Column("category", sa.String(120)),
        sa.Column("description", sa.Text),
        sa.Column("qualifications", sa.Text),
        sa.Column("how_to_apply", sa.Text),
        sa.Column("apply_url", sa.String(2048)),
        sa.Column("image_url", sa.String(2048)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("deadline", sa.Date),
        sa.Column("source_url", sa.String(2048), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="collected"),
        sa.Column("rejection_reasons", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("wp_post_id", sa.Integer),
        sa.Column("wp_link", sa.String(2048)),
        sa.Column("publish_attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_source_url", "jobs", ["source_url"], unique=True)
    op.create_table("logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("level", sa.String(10), nullable=False),
        sa.Column("event", sa.String(60), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("job_id", sa.Integer),
        sa.Column("source_id", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_logs_created", "logs", ["created_at"])
    op.create_table("settings",
        sa.Column("key", sa.String(80), primary_key=True),
        sa.Column("value", sa.JSON, nullable=False))

def downgrade():
    for t in ["settings", "logs", "jobs", "sources", "users"]:
        op.drop_table(t)
