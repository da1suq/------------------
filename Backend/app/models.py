from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from datetime import datetime, timezone
from app.database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    role = Column(String, default="participant")

class Contest(Base):
    __tablename__ = "contests"
    
    id = Column(Integer, primary_key=True, index=True)
    author_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String)
    description = Column(Text)
    start_at = Column(DateTime, nullable=True)
    end_at = Column(DateTime, nullable=True)
    difficulty = Column(String)
    mode = Column(String, default="duel")

class Task(Base):
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    contest_id = Column(Integer, ForeignKey("contests.id"))
    title = Column(String)
    description = Column(Text)
    example_input = Column(Text, nullable=True)
    example_output = Column(Text, nullable=True)

class Lobby(Base):
    __tablename__ = "lobbies"
    
    id = Column(Integer, primary_key=True, index=True)
    contest_id = Column(Integer, ForeignKey("contests.id"))
    creator_id = Column(Integer, ForeignKey("users.id"))
    mode = Column(String, default="duel")
    invitation_token = Column(String, unique=True, index=True)
    status = Column(String, default="waiting") # waiting, active, cancelled
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class Match(Base):
    __tablename__ = "matches"
    
    id = Column(Integer, primary_key=True, index=True)
    lobby_id = Column(Integer, ForeignKey("lobbies.id"))
    contest_id = Column(Integer, ForeignKey("contests.id"))
    mode = Column(String, default="duel")
    status = Column(String, default="waiting") # waiting, active, finished, cancelled
    start_at = Column(DateTime, nullable=True)
    end_at = Column(DateTime, nullable=True)

class Submission(Base):
    __tablename__ = "submissions"
    
    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"))
    task_id = Column(Integer, ForeignKey("tasks.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    code = Column(Text)
    language = Column(String, default="python")
    verdict = Column(String, default="running") # running, OK, WA, TLE, MLE, RE, CE
    submitted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class MatchResult(Base):
    __tablename__ = "match_results"
    
    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"))
    participant_id = Column(Integer, ForeignKey("users.id"))
    solved_count = Column(Integer, default=0)
    points = Column(Integer, default=0)