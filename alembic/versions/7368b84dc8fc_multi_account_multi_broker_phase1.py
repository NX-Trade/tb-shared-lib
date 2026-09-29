"""multi_account_multi_broker_phase1

Revision ID: 7368b84dc8fc
Revises: h1a2b3c4d5e6
Create Date: 2026-09-29 06:17:29.443833

Hand-trimmed from the raw ``alembic revision --autogenerate`` output: the raw
diff also picked up a batch of pre-existing, unrelated schema drift (stale
indexes on intraday_candle/index_yield/option_daily_metrics/news_embedding/
option_strategy_signal, a client_account unique-constraint naming mismatch,
fundamental_universe nullability, an unrelated trade/trading_order FK-naming
difference) that predates this change and is out of scope here. Only the
columns/tables/constraints introduced by the multi-account/multi-broker model
changes are included below.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '7368b84dc8fc'
down_revision: Union[str, None] = 'h1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'account_strategy_subscription',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('strategy_name', sa.String(length=50), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('risk_override', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['client_account.account_id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('account_id', 'strategy_name', name='uix_account_strategy'),
    )
    op.create_index(
        op.f('ix_account_strategy_subscription_account_id'),
        'account_strategy_subscription', ['account_id'], unique=False,
    )
    op.create_index(
        op.f('ix_account_strategy_subscription_strategy_name'),
        'account_strategy_subscription', ['strategy_name'], unique=False,
    )

    op.add_column('client_account', sa.Column('extra_credentials', sa.JSON(), nullable=True))
    op.add_column('client_account', sa.Column('daily_max_loss_limit', sa.Numeric(precision=14, scale=2), nullable=True))
    op.add_column('client_account', sa.Column('monthly_max_loss_limit', sa.Numeric(precision=14, scale=2), nullable=True))
    op.add_column('client_account', sa.Column('is_halted', sa.Boolean(), server_default='false', nullable=False))

    op.add_column('instrument', sa.Column('angelone_token', sa.String(length=20), nullable=True))
    op.create_index(op.f('ix_instrument_angelone_token'), 'instrument', ['angelone_token'], unique=False)

    # Widening only: any two rows unique under the old (trading_symbol, broker_id)
    # constraint remain unique under the new 3-column one, so this cannot fail
    # on existing data.
    op.drop_constraint(op.f('uix_position_symbol_broker'), 'position', type_='unique')
    op.create_unique_constraint(
        'uix_position_symbol_broker_account', 'position', ['trading_symbol', 'broker_id', 'account_id'],
    )

    op.add_column('system_metric', sa.Column('account_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_system_metric_account_id'), 'system_metric', ['account_id'], unique=False)
    op.create_foreign_key(
        'fk_system_metric_account_id', 'system_metric', 'client_account', ['account_id'], ['account_id'],
    )

    op.create_index(
        'ux_trading_order_signal_account_active', 'trading_order', ['signal_id', 'account_id'],
        unique=True, postgresql_where=sa.text("status NOT IN ('CANCELLED', 'REJECTED')"),
    )


def downgrade() -> None:
    op.drop_index('ux_trading_order_signal_account_active', table_name='trading_order', postgresql_where=sa.text("status NOT IN ('CANCELLED', 'REJECTED')"))

    op.drop_constraint('fk_system_metric_account_id', 'system_metric', type_='foreignkey')
    op.drop_index(op.f('ix_system_metric_account_id'), table_name='system_metric')
    op.drop_column('system_metric', 'account_id')

    op.drop_constraint('uix_position_symbol_broker_account', 'position', type_='unique')
    op.create_unique_constraint(op.f('uix_position_symbol_broker'), 'position', ['trading_symbol', 'broker_id'])

    op.drop_index(op.f('ix_instrument_angelone_token'), table_name='instrument')
    op.drop_column('instrument', 'angelone_token')

    op.drop_column('client_account', 'is_halted')
    op.drop_column('client_account', 'monthly_max_loss_limit')
    op.drop_column('client_account', 'daily_max_loss_limit')
    op.drop_column('client_account', 'extra_credentials')

    op.drop_index(op.f('ix_account_strategy_subscription_strategy_name'), table_name='account_strategy_subscription')
    op.drop_index(op.f('ix_account_strategy_subscription_account_id'), table_name='account_strategy_subscription')
    op.drop_table('account_strategy_subscription')
