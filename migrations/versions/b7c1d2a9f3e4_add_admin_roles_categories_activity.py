"""Add admin side: user roles/status, categories, activity log

Revision ID: b7c1d2a9f3e4
Revises: e4eb1f0ddac9
Create Date: 2026-10-10 15:30:00

Only ADDS columns/tables. No existing table is dropped or recreated, and every existing
user becomes an active plain "user" via the server defaults.
"""
from alembic import op
import sqlalchemy as sa


revision = 'b7c1d2a9f3e4'
down_revision = 'e4eb1f0ddac9'
branch_labels = None
depends_on = None

DEFAULT_CATEGORIES = [
    ("Food", "#f97316"), ("Groceries", "#84cc16"), ("Transport", "#0ea5e9"),
    ("Shopping", "#ec4899"), ("Bills", "#8b5cf6"), ("Rent", "#64748b"),
    ("Health", "#ef4444"), ("Education", "#14b8a6"), ("Entertainment", "#eab308"),
    ("Travel", "#6366f1"), ("Other", "#94a3b8"),
]


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('role', sa.String(length=20), nullable=False, server_default='user'))
        batch_op.add_column(sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_check_constraint('ck_users_role', "role IN ('user', 'admin')")

    categories = op.create_table(
        'categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('color', sa.String(length=7), nullable=False, server_default='#94a3b8'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    # Seed the built-in categories, plus any category name already used by existing expenses.
    op.bulk_insert(categories, [{"name": n, "color": c} for n, c in DEFAULT_CATEGORIES])
    op.execute(
        "INSERT INTO categories (name, color, is_active, created_at) "
        "SELECT DISTINCT e.category, '#94a3b8', true, now() FROM expenses e "
        "WHERE e.category NOT IN (SELECT name FROM categories)"
        if op.get_bind().dialect.name == "postgresql" else
        "INSERT INTO categories (name, color, is_active, created_at) "
        "SELECT DISTINCT e.category, '#94a3b8', 1, CURRENT_TIMESTAMP FROM expenses e "
        "WHERE e.category NOT IN (SELECT name FROM categories)"
    )

    op.create_table(
        'activity_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('actor_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('detail', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('activity_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_activity_logs_action'), ['action'], unique=False)
        batch_op.create_index(batch_op.f('ix_activity_logs_actor_id'), ['actor_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_activity_logs_created_at'), ['created_at'], unique=False)


def downgrade():
    op.drop_table('activity_logs')
    op.drop_table('categories')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('ck_users_role', type_='check')
        batch_op.drop_column('last_login_at')
        batch_op.drop_column('is_active')
        batch_op.drop_column('role')
