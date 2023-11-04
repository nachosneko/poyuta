# Standard libraries
import re
from datetime import datetime, timedelta

# Discord
import discord
from discord import app_commands
from discord.ext import commands

from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Database
from poyuta.database import User, Quiz, Answer, SessionFactory, initialize_database


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


def is_admin(user):
    with bot.session as session:
        admins = session.query(User).filter(User.is_admin == True).all()

    if user.id in [admin.id for admin in admins]:
        return True
    else:
        return False


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


@bot.event
async def on_ready():
    print(f"logged in as {bot.user.name}")

    initialize_database(config["DEFAULT_ADMIN_ID"], config["DEFAULT_ADMIN_NAME"])

    try:
        synced = await bot.tree.sync()
        print(f"synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        post_yesterdays_quiz_results, "cron", hour=18, minute=0, second=0
    )  # Schedule at 19:00:00
    scheduler.start()


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
    """*Admin only* - create a new quiz."""

    if not is_admin(interaction.user):
        await interaction.response.send_message(
            "you are not an admin, you can't use this command"
        )
        return

    # get latest quiz from database
    with bot.session as session:
        latest_quiz = session.query(Quiz).order_by(Quiz.date.desc()).first()
        # latest quiz date is the date of the latest quiz if it exists, else it defaults to yesterday
        if latest_quiz:
            latest_quiz_date = latest_quiz.date
        else:
            latest_quiz_date = datetime.now() - timedelta(days=1)
            latest_quiz_date = latest_quiz_date.date()

    # get current date
    current_date = datetime.now().date()

    # if the current date is before the latest quiz date
    # that means there's already a quiz for today, so set the new date to the latest quiz date + 1 day
    if current_date <= latest_quiz_date:
        new_date = latest_quiz_date + timedelta(days=1)
    # else set the new date to the current date
    else:
        new_date = current_date

    # add the new quiz to database
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

    await interaction.response.send_message(f"new quiz created for {new_date}")


@bot.tree.command(name="updatequiz")
@app_commands.describe(
    date="date of the quiz to update in YYYY-MM-DD format",
    new_female_clip="input new clip for female",
    new_correct_female="input new seiyuu for female clip",
    new_male_clip="input new clip for male",
    new_correct_male="input new seiyuu for male clip",
)
async def updatequiz(
    interaction: discord.Interaction,
    date: str,
    new_female_clip: str,
    new_correct_female: str,
    new_male_clip: str,
    new_correct_male: str,
):
    """*Admin only* - Update a planned quiz."""

    if not is_admin(interaction.user):
        await interaction.response.send_message(
            "You are not an admin, you can't use this command."
        )
        return

    try:
        date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        await interaction.response.send_message(
            "Invalid date format. Please use YYYY-MM-DD."
        )
        return

    # check the date is in the future
    if date <= datetime.now().date():
        await interaction.response.send_message(
            "You can only update a quiz that hasn't happened yet. Please use a date in the future."
        )
        return

    # check the quiz exists
    with bot.session as session:
        quiz = session.query(Quiz).filter(Quiz.date == date).first()

        if not quiz:
            await interaction.response.send_message("No quiz for this date.")
            return

        # Update attributes
        quiz.female_clip = new_female_clip
        quiz.female_answer = new_correct_female
        quiz.male_clip = new_male_clip
        quiz.male_answer = new_correct_male

        # Commit the changes to the database
        session.commit()

        await interaction.response.send_message(f"Quiz updated for {date}")


@bot.tree.command(name="plannedquizzes")
@app_commands.describe()
async def male(interaction: discord.Interaction):
    """*Admin only* - Check the planned quizzes."""

    if not is_admin(interaction.user):
        await interaction.response.send_message(
            "You are not an admin, you can't use this command"
        )
        return

    today = datetime.now().date()

    with bot.session as session:
        quizzes = session.query(Quiz).filter(Quiz.date >= today).all()

        if not quizzes:
            await interaction.response.send_message("No planned quizzes")
            return

        planned_quizzes = "\n\n".join(
            [
                f"### {quiz.date} :\n \
                - Female : {quiz.female_clip} {quiz.female_answer}\n \
                - Male : {quiz.male_clip} {quiz.male_answer}"
                for quiz in quizzes
            ]
        )
        await interaction.response.send_message(planned_quizzes)


@bot.event
async def post_yesterdays_quiz_results():
    channel_id = 366643056138518532  # Replace with the actual channel ID
    channel = bot.get_channel(channel_id)

    if not channel:
        print("channel not found.")
        return

    # Calculate the date for yesterday
    yesterday = datetime.now() - timedelta(days=1)

    # Query the database for the quiz that matches the calculated date
    with bot.session as session:
        quiz = session.query(Quiz).filter(Quiz.date == yesterday.date()).first()
        answer = session.query(Answer).filter(Answer.user).first()

    if not quiz:
        print("quiz not found for yesterday.")
        return

    embed = discord.Embed(
        title="Yesterday's Quiz Results",
        color=0xBBE6F3,
    )
    embed.set_author(
        name=config["NEWQUIZ_EMBED_AUTHOR"], icon_url="https://i.imgur.com/6uKnKMS.png"
    )

    embed.add_field(name="Male", value=f"||{quiz.male_answer}||", inline=True)
    embed.add_field(name="Clip", value=quiz.male_clip, inline=True)

    embed.add_field(name="", value="", inline=False)

    embed.add_field(name="Female", value=f"||{quiz.female_answer}||", inline=True)
    embed.add_field(name="Clip", value=quiz.female_clip, inline=True)

    embed.add_field(name="", value="", inline=False)

    embed.add_field(
        name="Top Guessers",
        value=f"\n{answer.user_id}\nValue 1 Line 2\nValue 1 Line 3",
        inline=True,
    )

    embed.add_field(name="Time(?)", value="TBA", inline=True)
    embed.add_field(name="Attempts", value="TBA", inline=True)
    embed.add_field(name="Most Guessed (Male)", value="TBA", inline=False)
    embed.add_field(name="Most Guessed (Female)", value="TBA", inline=False)

    await channel.send(embed=embed)


@bot.command()
async def postquizresults(ctx):
    await post_yesterdays_quiz_results()
    await ctx.send("(yesterdays quiz)")


@bot.tree.command(name="female")
@app_commands.describe(seiyuu="guess the female seiyuu")
async def female(interaction: discord.Interaction, seiyuu: str):
    """guess the seiyuu for the current female clip."""

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
        await interaction.response.send_message("✅")

        # Store the user's answer in the Answer table
        with bot.session as session:
            user_answer.is_correct = True
            session.add(user_answer)
            session.commit()

    # Otherwise, the pattern doesn't match : the answer is incorrect
    else:
        # Send feedback to the user
        await interaction.response.send_message("❌")

        # Store the user's answer in the Answer table
        with bot.session as session:
            user_answer.is_correct = False
            session.add(user_answer)
            session.commit()


@bot.tree.command(name="male")
@app_commands.describe(seiyuu="guess the male seiyuu")
async def male(interaction: discord.Interaction, seiyuu: str):
    """guess the seiyuu for the current male clip."""

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
        await interaction.response.send_message("✅")

        # Store the user's answer in the Answer table
        with bot.session as session:
            user_answer.is_correct = True
            session.add(user_answer)
            session.commit()

    # Otherwise, the pattern doesn't match : the answer is incorrect
    else:
        # Send feedback to the user
        await interaction.response.send_message("❌")

        # Store the user's answer in the Answer table
        with bot.session as session:
            user_answer.is_correct = False
            session.add(user_answer)
            session.commit()
