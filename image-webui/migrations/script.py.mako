"""Revision script template

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "\n    with op.batch_alter_table('images') as batch_op:\n        batch_op.add_column(sa.Column('checksum', sa.String(), nullable=True))\n        try:\n            batch_op.create_index('ix_images_checksum', ['checksum'])\n        except Exception:\n            pass\n    "}


def downgrade() -> None:
    ${downgrades if downgrades else "\n    with op.batch_alter_table('images') as batch_op:\n        try:\n            batch_op.drop_index('ix_images_checksum')\n        except Exception:\n            pass\n        batch_op.drop_column('checksum')\n    "}
