import enum
from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, Enum
from sqlalchemy.orm import relationship
from .base import Base


class RoomType(enum.Enum):
    simple = 1
    random = 2
    fav = 3


class Room(Base):
    __tablename__ = 'rooms'
    
    id = Column(Integer(), primary_key=True)
    key = Column(String(36), index=True)
    name = Column(String(255))
    room_type = Column(Enum(RoomType, validate_strings=True), default=RoomType.simple)
    allow_downvote = Column(Boolean(), default=True)
    downvote_threeshold = Column(Integer(), default=3)
    admin = Column(String(36))
    songs = relationship('Song', back_populates='songs')
    limit_per_user = Column(Boolean(), default=False)
    max_per_user = Column(Integer(), default=10)
