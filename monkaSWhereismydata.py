import json
from datetime import datetime, timedelta
from poyuta.database import (
    SubmissionChannels,
    QuizChannels,
    User,
    QuizType,
    Quiz,
    Answer,
    UserStartQuizTimestamp,
)
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
import re
import pandas as pd

DAILY_QUIZ_RESET_TIME = datetime.strptime("19:00:00", "%H:%M:%S")


# Créez une connexion à la base de données
engine = sa.create_engine("sqlite:///database/poyuta.db")
conn = engine.connect()
session = sessionmaker(bind=engine)()


author_exceptions_mapping = {
    "hieda.nene": "574624086169485331",
    "rie_takahashi": "161026455696834560",
    "mafumoko": "217755086670004224",
    # To fix pfp
    "neoburnz": "336535900538404894",
    "mathlm": "446370895649308673",
    "flowien_xix": "1168123322479947898",
}

with open("database/messagesFinal.json") as f:
    data = json.load(f)


def extract_user_from_name(author, pfp):

    if author in author_exceptions_mapping:
        user_id = author_exceptions_mapping[author]
        user = session.query(User).filter(User.id == user_id).first()

        if not user:
            new_user = User(id=user_id, name=author, pfp=pfp, is_admin=False)
            session.add(new_user)
            session.commit()
            user = new_user

    else:
        users = session.query(User).filter(User.name == author).all()

        if len(users) > 1:
            print(f"Multiple users found for {author}")
            return None

        if len(users) == 0:
            print(f"No user found for {author}")
            return None

        user = users[0]

    if not user:
        print(f"User {author} not found")
        exit()
        return None

    return user


def deduce_caps_routine(user_id):

    # extract a snippet of last 500 answers from users
    # check whether he uses full lowercase or note
    answers = session.query(Answer).filter(Answer.user_id == user_id).all()

    if len(answers) == 0:
        return "Lowercase"

    nb_lowercase = 0
    nb_uppercase = 0

    answers_already_done = set()

    for answer in answers:

        check_answer = answer.answer

        if answer.answer == "\\Bonus Answer\\":
            check_answer = answer.bonus_answer

        if check_answer is None:
            continue

        if check_answer in answers_already_done:
            continue

        answers_already_done.add(check_answer)

        if check_answer.islower():
            nb_lowercase += 1
        else:
            nb_uppercase += 1

    return "Lowercase" if nb_lowercase > nb_uppercase else "Uppercase"


# add back quizzes to database
# load the spreadsheet database/FixingQuizzes.ods in sheet "QUIZ SHEET" in a pandas dataframe
df = pd.read_excel("database/FixingQuizzes.ods", engine="odf", sheet_name="QUIZ SHEET")

# iterate of df rows
for index, row in df.iterrows():

    date = row["Date"]
    if type(date) == str:
        date = datetime.strptime(f"2024-{date.replace('/', '-')}", "%Y-%d-%m")
        # convert date to Y-m-d format
        date = date.date()
    else:
        date = date.date()
        if "08" in str(date):
            date = datetime.strptime(str(date), "%Y-%d-%m").date()

    male_creator = row["Male Creator"]
    male_creator = session.query(User).filter(User.id == male_creator).first()
    male_answer = row["Male Answer"]
    male_bonus_answer = row["Male Bonus_Answer"]
    male_clip = row["Male Clip"]

    new_quiz_male = Quiz(
        creator_id=male_creator.id,
        clip=male_clip,
        answer=male_answer,
        bonus_answer=male_bonus_answer,
        date=date,
        id_type=1,
    )

    session.add(new_quiz_male)

    female_creator = row["Female Creator"]
    female_creator = session.query(User).filter(User.id == female_creator).first()
    female_answer = row["Female Answer"]
    female_bonus_answer = row["Female Bonus_Answer"]
    female_clip = row["Female Clip"]

    new_quiz_female = Quiz(
        creator_id=female_creator.id,
        clip=female_clip,
        answer=female_answer,
        bonus_answer=female_bonus_answer,
        date=date,
        id_type=2,
    )

    session.add(new_quiz_female)
    session.commit()


# deduce info from the embed content
for message in data["messages"]:

    answer_datetime = datetime.fromisoformat(message["timestamp"])
    answer_datetime = answer_datetime + timedelta(hours=2)
    message["timestamp"] = answer_datetime

    quiz_date = (
        answer_datetime.date() - timedelta(days=1)
        if answer_datetime.time() < DAILY_QUIZ_RESET_TIME.time()
        else answer_datetime.date()
    )

    message["quiz_date"] = str(quiz_date)

    gender = (
        "Male"
        if "Male" in message["quiz_type"]
        else "Female" if "Female" in message["quiz_type"] else None
    )

    correct = False if "Incorrect" in message["content"] else True

    bonus = (
        True
        if (correct and "you can also try" not in message["content"])
        or (not correct and "Still no bonus" in message["content"])
        else False
    )

    message["type"] = gender
    message["correct"] = correct
    message["bonus"] = bonus

    if correct:
        # answer time is given like so : 'Correct in 17.327s!'
        # define a regex to extract the numbers between 'Correct in' and '!'

        regx = re.compile(r"Correct in (\d+\.\d+)s!")
        answer_time = float(regx.search(message["content"]).group(1))

        message["answer_time"] = answer_time


user_start_quiz_metadata = {}
user_caps_routine = {}

# add back to database
for message in data["messages"]:

    author = message["embed_author_name"]
    pfp = message["embed_author_icon"]

    user = extract_user_from_name(author, pfp)

    if user.id not in user_start_quiz_metadata:
        user_start_quiz_metadata[user.id] = {}

    if user.id not in user_caps_routine:
        caps_routine = deduce_caps_routine(user.id)
        user_caps_routine[user.id] = caps_routine

    quiz_type = 1 if message["type"] == "Male" else 2
    quiz = (
        session.query(Quiz)
        .filter(Quiz.date == message["quiz_date"])
        .filter(Quiz.id_type == quiz_type)
        .first()
    )

    if quiz.id not in user_start_quiz_metadata[user.id]:
        user_start_quiz_metadata[user.id][quiz.id] = []

    user_start_quiz_metadata[user.id][quiz.id].append(
        {
            "time": message["timestamp"],
            "correct": message["correct"],
            "answer_time": message["answer_time"] if message["correct"] else None,
        }
    )

    if "answer_time" in message and message["answer_time"] == 11.193:
        print(quiz_type)

    if message["correct"]:

        if message["bonus"]:

            deduced_answer = (
                quiz.bonus_answer.lower()
                if user_caps_routine[user.id] == "Lowercase"
                else quiz.bonus_answer
            )

            # print(deduced_answer)

            new_answer = Answer(
                quiz_id=quiz.id,
                user_id=user.id,
                answer="\\Bonus Answer\\",
                is_correct=False,
                bonus_answer=deduced_answer,
                is_bonus_point=True,
                answer_time=message["answer_time"],
            )
        else:

            deduced_answer = (
                quiz.answer.lower()
                if user_caps_routine[user.id] == "Lowercase"
                else quiz.answer
            )

            # print(deduced_answer)

            new_answer = Answer(
                quiz_id=quiz.id,
                user_id=user.id,
                answer=deduced_answer,
                is_correct=True,
                bonus_answer=None,
                is_bonus_point=False,
                answer_time=message["answer_time"],
            )
    else:
        if message["bonus"]:
            new_answer = Answer(
                quiz_id=quiz.id,
                user_id=user.id,
                answer="\\Bonus Answer\\",
                is_correct=False,
                bonus_answer="UnknownWrong",
                is_bonus_point=False,
                answer_time=69.696,
            )
        else:
            new_answer = Answer(
                quiz_id=quiz.id,
                user_id=user.id,
                answer="UnknownWrong",
                is_correct=False,
                bonus_answer=None,
                is_bonus_point=False,
                answer_time=69.696,
            )

    session.add(new_answer)

# Deduce the UserStartQuizTimestamp
for user_id, quizzes in user_start_quiz_metadata.items():
    for quiz_id, answers in quizzes.items():

        # check this userstartquiz doesn't already exist
        user_start = (
            session.query(UserStartQuizTimestamp)
            .filter(UserStartQuizTimestamp.user_id == user_id)
            .filter(UserStartQuizTimestamp.quiz_id == quiz_id)
            .first()
        )

        if user_start:
            continue

        if len(answers) == 0:
            continue

        flag_correct_found = False
        # check if there's a correct answer
        for answer in answers:
            if answer["correct"]:
                flag_correct_found = True
                break

        if flag_correct_found:
            # the user start quiz timestamp is their first correct answer minus the answer time
            first_correct_answer = next(
                answer for answer in answers if answer["correct"]
            )
            time = first_correct_answer["time"]

            user_start_quiz_timestamp = time - timedelta(
                seconds=first_correct_answer["answer_time"]
            )
        else:
            # otherwise, let's arbitrarily set it to the first answer given minus 30seconds
            time = answers[0]["time"]
            user_start_quiz_timestamp = time - timedelta(seconds=30)

        new_user_start_quiz_timestamp = UserStartQuizTimestamp(
            user_id=user_id, quiz_id=quiz_id, timestamp=user_start_quiz_timestamp
        )
        session.add(new_user_start_quiz_timestamp)

session.commit()
