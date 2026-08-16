from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.sql import func

from app.db.session import Base


class OfferComparison(Base):
    __tablename__ = "offer_comparisons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    offer_a_id = Column(Integer, ForeignKey("offers.id", ondelete="RESTRICT"), nullable=False, index=True)
    offer_b_id = Column(Integer, ForeignKey("offers.id", ondelete="RESTRICT"), nullable=False, index=True)
    title = Column(String(300), nullable=False)
    status = Column(String(20), nullable=False, default="current", index=True)
    preference_snapshot = Column(JSON, nullable=False, default=dict)
    assumption_snapshot = Column(JSON, nullable=False, default=dict)
    offer_snapshot = Column(JSON, nullable=False, default=dict)
    result_snapshot = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
