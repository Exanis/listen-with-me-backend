from sqlalchemy import Column, String, Integer, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base


class Song(Base):
    __tablename__ = 'songs'
    
    id = Column(Integer(), primary_key=True)
    url = Column(String(2048))
    name = Column(String(255))
    added_by = Column(String(255), default='')
    added_id = Column(String(255), default='')
    order = Column(Integer())
    played = Column(Integer(), default=-1)
    upvotes = Column(Integer(), default=0)
    downvotes = Column(Integer(), default=0)
    room_id = Column(Integer(), ForeignKey('rooms.id'))
    room = relationship('Room', back_populates='room')
