import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from pathlib import Path

# Define a unique name for the User class
Base = declarative_base()

# SQLAlchemy setup
DATABASE_PATH = Path("database")
DATABASE_PATH.mkdir(exist_ok=True)

DATABASE_URL = f"sqlite:///{DATABASE_PATH}/poyuta.db"
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}, echo=True
)
SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Define the Quiz class
class Quiz(Base):
    __tablename__ = "quiz"
    id = sa.Column(sa.Integer, primary_key=True)
    female_answer = sa.Column(sa.String, nullable=False)
    female_clip = sa.Column(sa.String, nullable=False)
    male_answer = sa.Column(sa.String, nullable=False)
    male_clip = sa.Column(sa.String, nullable=False)


# Define the User class
class User(Base):
    __tablename__ = "users"
    id = sa.Column(sa.Integer, primary_key=True)
    discord_id = sa.Column(sa.Integer, unique=True, nullable=False)
    name = sa.Column(sa.String, nullable=False)


# Define the Answer class with a unique backref name
class Answer(Base):
    __tablename__ = "answers"
    id = sa.Column(sa.Integer, primary_key=True)
    user_id = sa.Column(sa.Integer, sa.ForeignKey(User.id))
    quiz_id = sa.Column(sa.Integer, sa.ForeignKey(Quiz.id))
    answer = sa.Column(sa.String, nullable=False)
    answer_type = sa.Column(sa.String, nullable=False)
    is_correct = sa.Column(sa.Boolean, nullable=False)
    user = relationship("User", backref="user_answers")  # Use a unique name
    quiz = relationship("Quiz", backref="answers")


# Create the tables
Base.metadata.create_all(bind=engine)
