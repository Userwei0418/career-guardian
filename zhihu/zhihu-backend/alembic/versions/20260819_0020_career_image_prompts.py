"""Store administrator-managed career image style and scene prompts."""

from alembic import op
import sqlalchemy as sa


revision = "20260819_0020"
down_revision = "20260819_0019"
branch_labels = None
depends_on = None


STYLE_PROMPT = (
    "克制、温暖、可信的 2.5D 编辑插画；软陶与纸张质感；主色为玉石绿和深青色，"
    "辅以少量钴蓝、珊瑚橙、暖黄色；自然柔光，大面积留白，细节精致但不拥挤。"
)
LANDSCAPE_PROMPT = (
    "16:9 横向首页主视觉。人物位于画面右侧三分之一，左侧保留大面积干净留白供界面文字叠加；"
    "远近层次清楚，适合桌面与移动端安全裁切。"
)
SQUARE_PROMPT = "1:1 方形个人中心插画。主体居中偏下，四周留有呼吸空间，适合圆角卡片裁切。"


def _add_populated_text(column_name: str, value: str) -> None:
    op.add_column("ai_provider_settings", sa.Column(column_name, sa.Text(), nullable=True))
    op.execute(
        sa.text(f"UPDATE ai_provider_settings SET {column_name} = :value WHERE {column_name} IS NULL")
        .bindparams(value=value)
    )
    op.alter_column(
        "ai_provider_settings",
        column_name,
        existing_type=sa.Text(),
        nullable=False,
    )


def upgrade():
    _add_populated_text("image_style_prompt", STYLE_PROMPT)
    _add_populated_text("image_landscape_prompt", LANDSCAPE_PROMPT)
    _add_populated_text("image_square_prompt", SQUARE_PROMPT)


def downgrade():
    op.drop_column("ai_provider_settings", "image_square_prompt")
    op.drop_column("ai_provider_settings", "image_landscape_prompt")
    op.drop_column("ai_provider_settings", "image_style_prompt")
