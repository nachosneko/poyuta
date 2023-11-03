# Standard libraries
import re
from datetime import datetime, timedelta

# Discord
import discord
from discord import app_commands
from discord.ext import commands

# Database
from poyuta.database import User, Quiz, Answer, SessionFactory

# Utils
from poyuta.utils import (
    load_environment,
    process_user_input,
    get_current_quiz,
    get_user_from_id,
)


config = load_environment()

intents = discord.Intents.all()
intents.reactions = True
intents.messages = True


# Update your bot class to include the session property
class PoyutaBot(commands.Bot):
    def __init__(self, command_prefix, intents):
        super().__init__(command_prefix=command_prefix, intents=intents)

    # add database session to bot
    # can now be access through bot.session
    @property
    def session(self):
        return SessionFactory()


# Instantiate your bot
bot = PoyutaBot(command_prefix="!", intents=intents)

admin_user_ids = [
    195534572581158913,
    240181741703266304,
]  # Replace with the admin user IDs
# TODO : define in database ? Possibility to add new admin id from commands ?
# TODO : hide commands if user is not admin


# Function to change the quiz audio and correct answer
async def change_female(new_female_clip, new_correct_female):
    global current_female_clip, correct_female
    current_female_clip = new_female_clip
    correct_female = new_correct_female


async def change_male(new_male_clip, new_correct_male):
    global current_male_clip, correct_male
    current_male_clip = new_male_clip
    correct_male = new_correct_male


@bot.event
async def on_ready():
    print(f"logged in as {bot.user.name}")
    try:
        synced = await bot.tree.sync()
        print(f"synced {len(synced)} command(s)")
    except Exception as e:
        print(e)


@bot.command()
async def currentclips(ctx):
    if current_female_clip:
        await ctx.send(current_female_clip)
    if current_male_clip:
        await ctx.send(current_male_clip)
    else:
        await ctx.send("no clips in progress")


@bot.tree.command(name="newquiz")
@app_commands.describe(
    new_female_clip="input new clip for female",
    new_correct_female="input new seiyuu for female clip",
    new_male_clip="input new clip for male",
    new_correct_male="input new seiyuu for male clip",
)
async def newquiz(
    interaction: discord.Interaction,
    new_female_clip: str,
    new_correct_female: str,
    new_male_clip: str,
    new_correct_male: str,
):
    """Create a new quiz."""

    # get latest quiz from database
    with bot.session as session:
        latest_quiz = session.query(Quiz).order_by(Quiz.date.desc()).first()
        # latest quiz date is the date of the latest quiz if it exists, else it defaults to yesterday
        if latest_quiz:
            latest_quiz_date = latest_quiz.date
        else:
            latest_quiz_date = datetime.now() - timedelta(days=1)

    # get current date
    current_date = datetime.now().date()

    # if the current date is before the latest quiz date
    # that means there's already a quiz for today, so set the new date to the latest quiz date + 1 day
    if current_date <= latest_quiz_date:
        new_date = latest_quiz_date + timedelta(days=1)
    # else set the new date to the current date
    else:
        new_date = current_date

    # if not an admin : return
    if interaction.user.id not in admin_user_ids:
        await interaction.response.send_message("only admins can change the clips")
    else:
        # add new quiz to database
        with bot.session as session:
            new_quiz = Quiz(
                female_clip=new_female_clip,
                female_answer=new_correct_female,
                male_clip=new_male_clip,
                male_answer=new_correct_male,
                date=new_date,
            )
            session.add(new_quiz)
            session.commit()

        await interaction.response.send_message("clips updated")


@bot.tree.command(name="female")
@app_commands.describe(seiyuu="guess the female seiyuu")
async def female(interaction: discord.Interaction, seiyuu: str):
    """Guess the seiyuu for the current female clip."""

    quiz = get_current_quiz(bot.session)

    if not quiz:
        await interaction.response.send_message("no quiz today :(")

    user = get_user_from_id(
        bot_session=bot.session,
        user_id=interaction.user.id,
        user_name=interaction.user.name,
        add_if_not_exist=True,
    )

    # create the answer object
    user_answer = Answer(
        user_id=user.id,
        quiz_id=quiz.id,
        answer=seiyuu,
        answer_type="female",
    )

    # Generate a pattern to match with the correct answer
    user_answer_pattern = process_user_input(seiyuu)

    # If the pattern matches : the answer is correct
    if re.search(user_answer_pattern, quiz.female_answer):
        # Send feedback to the user
        await interaction.response.send_message(
            ":fearful: you guessed it **correctly**"
        )

        # Store the user's answer in the Answer table
        with bot.session as session:
            user_answer.is_correct = True
            session.add(user_answer)
            session.commit()

    # Otherwise, the pattern doesn't match : the answer is incorrect
    else:
        # Send feedback to the user
        await interaction.response.send_message("**incorrect** :skull:")

        # Store the user's answer in the Answer table
        with bot.session as session:
            user_answer.is_correct = False
            session.add(user_answer)
            session.commit()


@bot.tree.command(name="male")
@app_commands.describe(seiyuu="guess the male seiyuu")
async def male(interaction: discord.Interaction, seiyuu: str):
    """Guess the seiyuu for the current male clip."""

    quiz = get_current_quiz(bot.session)

    if not quiz:
        await interaction.response.send_message("no quiz today :(")

    user = get_user_from_id(
        bot_session=bot.session,
        user_id=interaction.user.id,
        user_name=interaction.user.name,
        add_if_not_exist=True,
    )

    # create the answer object
    user_answer = Answer(
        user_id=user.id,
        quiz_id=quiz.id,
        answer=seiyuu,
        answer_type="male",
    )

    # Generate a pattern to match with the correct answer
    user_answer_pattern = process_user_input(seiyuu)

    # If the pattern matches : the answer is correct
    if re.search(user_answer_pattern, quiz.male_answer):
        # Send feedback to the user
        await interaction.response.send_message(
            ":fearful: you guessed it **correctly**"
        )

        # Store the user's answer in the Answer table
        with bot.session as session:
            user_answer.is_correct = True
            session.add(user_answer)
            session.commit()

    # Otherwise, the pattern doesn't match : the answer is incorrect
    else:
        # Send feedback to the user
        await interaction.response.send_message("**incorrect** :skull:")

        # Store the user's answer in the Answer table
        with bot.session as session:
            user_answer.is_correct = False
            session.add(user_answer)
            session.commit()
