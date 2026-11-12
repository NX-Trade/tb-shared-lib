"""add news.sectors

The sectors a news item is about, as the sector indices' own symbols (comma-separated, e.g.
``NIFTYIT,CNXPHRM``), set when the item is collected from the stocks it names and from sector words in
its text. Nullable: an item about no sector, and every item collected before this, has none until
``scripts/16_retag_news_symbols.py`` fills the existing ones in.

Revision ID: a2b3c4d5e6f7
Revises: z1a2b3c4d5f6
Create Date: 2026-11-12 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = 'z1a2b3c4d5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('news', sa.Column('sectors', sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column('news', 'sectors')
