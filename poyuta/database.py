# standard libraries
from pathlib import Path

# SQLAlchemy
import sqlalchemy as sa
from sqlalchemy import create_engine, inspect, UniqueConstraint, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

# Define a unique name for the User class
Base = declarative_base()

# SQLAlchemy setup
DATABASE_PATH = Path("database")
DATABASE_PATH.mkdir(exist_ok=True)

DATABASE_URL = f"sqlite:///{DATABASE_PATH}/poyuta.db"
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}, echo=False
)
SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

INITIAL_QUIZ_TYPES = [
    {
        "type": "Male Seiyuu",
        "emoji": ":male_sign:",
    },
    {
        "type": "Female Seiyuu",
        "emoji": ":female_sign:",
    },
    {
        "type": "Male Image",
        "emoji": ":frame_photo:",
    },
    {
        "type": "Female Image",
        "emoji": ":frame_photo:",
    },
    {
        "type": "Song",
        "emoji": ":microphone2: ",
    },
]


class QuizChannels(Base):
    __tablename__ = "quiz_channels"

    id_server = sa.Column(sa.Integer, primary_key=True)
    id_channel = sa.Column(sa.Integer, nullable=False)


class SubmissionChannels(Base):
    __tablename__ = "submission_channels"

    id_sub_server = sa.Column(sa.Integer, primary_key=True)
    id_sub_channel = sa.Column(sa.Integer, nullable=False)


class User(Base):
    __tablename__ = "users"
    id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String, nullable=False)
    pfp = sa.Column(sa.String, nullable=True)
    is_admin = sa.Column(sa.Boolean, nullable=False, default=False)


class QuizType(Base):
    __tablename__ = "quiz_type"

    id = sa.Column(sa.Integer, primary_key=True)
    type = sa.Column(sa.String, nullable=False, unique=True)
    emoji = sa.Column(sa.String, nullable=False)


# Define the Quiz class
class Quiz(Base):
    __tablename__ = "quizzes"
    id = sa.Column(sa.Integer, primary_key=True)
    creator_id = sa.Column(sa.Integer, sa.ForeignKey(User.id), nullable=False)
    creator = relationship(User, backref="quizzes_created")

    clip = sa.Column(sa.String, nullable=False)
    answer = sa.Column(sa.String, nullable=False)
    bonus_answer = sa.Column(sa.String, nullable=True)

    date = sa.Column(sa.Date, nullable=False)
    id_type = sa.Column(sa.Integer, sa.ForeignKey(QuizType.id))
    type = relationship(QuizType, backref="quizzes")

    # ensure there's only one type of quiz per day
    __table_args__ = (UniqueConstraint("date", "id_type", name="uq_date_type"),)


# Define the Answer class
class Answer(Base):
    __tablename__ = "answers"
    id = sa.Column(sa.Integer, primary_key=True)

    quiz_id = sa.Column(sa.Integer, sa.ForeignKey(Quiz.id))
    quiz = relationship(Quiz, backref="answers")

    user_id = sa.Column(sa.Integer, sa.ForeignKey(User.id))
    user = relationship(User, backref="answers")

    answer = sa.Column(sa.String, nullable=False)
    is_correct = sa.Column(sa.Boolean, nullable=False)

    bonus_answer = sa.Column(sa.String, nullable=True)
    is_bonus_point = sa.Column(sa.Boolean, nullable=False)

    answer_time = sa.Column(sa.Float, nullable=False)


class UserStartQuizTimestamp(Base):
    __tablename__ = "user_start_quiz_timestamp"

    id = sa.Column(sa.Integer, primary_key=True)

    user_id = sa.Column(sa.Integer, sa.ForeignKey(User.id), nullable=False)
    user = relationship(User, backref="start_quizzes_timestamps")

    quiz_id = sa.Column(sa.Integer, sa.ForeignKey(Quiz.id), nullable=False)
    quiz = relationship(Quiz, backref="start_quiz_timestamps")

    # answer time in seconds
    timestamp = sa.Column(sa.DateTime, nullable=False)

    # ensure there's only one start quiz timestamp per user per quiz
    __table_args__ = (UniqueConstraint("user_id", "quiz_id", name="uq_userid_quizid"),)


def initialize_database(
    default_admin_id: id, default_admin_name: str, use_historic_data: bool = False
):
    inspector = inspect(engine)

    if (
        not inspector.has_table("users")
        or not inspector.has_table("quizzes")
        or not inspector.has_table("user_start_quiz_timestamp")
    ):
        # Create the tables
        Base.metadata.create_all(bind=engine)

        # Create a session
        with SessionFactory() as session:
            # add the default admin user
            default_admin = User(
                id=default_admin_id, name=default_admin_name, is_admin=True
            )
            session.add(default_admin)
            print(f"Default admin user ({default_admin_name}) created.")

            for initial_quiz_type in INITIAL_QUIZ_TYPES:
                session.add(
                    QuizType(
                        type=initial_quiz_type["type"], emoji=initial_quiz_type["emoji"]
                    )
                )
                print(f"Initial quiz type '{initial_quiz_type}' created.")

            if use_historic_data:
                # get the sql script
                with open(DATABASE_PATH / "historic_quiz_data.sql") as f:
                    sql_script = f.read()

                    # Split the script into individual statements
                    statements = sql_script.split(";")

                    # Execute each statement
                    for statement in statements:
                        if statement.strip():  # Skip empty statements
                            session.execute(text(statement.strip()))

            session.commit()
