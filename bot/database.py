import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from pathlib import Path

DATABASE_PATH = Path("database")
# create the folder if it doesn't exist
DATABASE_PATH.mkdir(exist_ok=True)

# SQLAlchemy setup
DATABASE_URL = f"sqlite:///{DATABASE_PATH}/poyuta.db"
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}, echo=True
)  # echo=True for debugging
# Create a session factory function
SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Declarative base for declarative class definitions
Base = declarative_base()


class Quiz(Base):
    __tablename__ = "quiz"
    id = sa.Column(sa.Integer, primary_key=True)

    female_answer = sa.Column(sa.String, nullable=False)
    female_clip = sa.Column(sa.String, nullable=False)

    male_answer = sa.Column(sa.String, nullable=False)
    male_clip = sa.Column(sa.String, nullable=False)


class User(Base):
    __tablename__ = "users"
    id = sa.Column(sa.Integer, primary_key=True)

    discord_id = sa.Column(sa.Integer, unique=True, nullable=False)
    name = sa.Column(sa.String, nullable=False)


class Answer(Base):
    __tablename__ = "answers"
    id = sa.Column(sa.Integer, primary_key=True)

    # User relationship
    user_id = sa.Column(sa.Integer, sa.ForeignKey(User.id))
    user = relationship(User, backref="answers")

    # Quiz relationship
    quiz_id = sa.Column(sa.Integer, sa.ForeignKey(Quiz.id))
    quiz = relationship(Quiz, backref="answers")

    # answers
    answer = sa.Column(sa.String)


Base.metadata.create_all(bind=engine)
