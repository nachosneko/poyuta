# standard libraries
from pathlib import Path

# SQLAlchemy
import sqlalchemy as sa
from sqlalchemy import create_engine, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

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
    date = sa.Column(sa.Date, nullable=False)


# Define the User class
class User(Base):
    __tablename__ = "users"
    id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String, nullable=False)
    is_admin = sa.Column(sa.Boolean, nullable=False, default=False)


# Define the Answer class with a unique backref name
class Answer(Base):
    __tablename__ = "answers"
    id = sa.Column(sa.Integer, primary_key=True)

    quiz_id = sa.Column(sa.Integer, sa.ForeignKey(Quiz.id))
    quiz = relationship(Quiz, backref="answers")

    user_id = sa.Column(sa.Integer, sa.ForeignKey(User.id))
    user = relationship(User, backref="answers")

    answer = sa.Column(sa.String, nullable=False)
    answer_type = sa.Column(sa.String, nullable=False)
    is_correct = sa.Column(sa.Boolean, nullable=False)


def initialize_database(default_admin_id, default_admin_name):
    inspector = inspect(engine)

    if not inspector.has_table("users") or not inspector.has_table("quiz"):
        # Create the tables
        Base.metadata.create_all(bind=engine)

        # Create a session
        session = SessionFactory()

        # add the default admin user
        default_admin = User(
            id=default_admin_id, name=default_admin_name, is_admin=True
        )
        session.add(default_admin)
        session.commit()

        print(f"Default admin user ({default_admin_name}) created.")
