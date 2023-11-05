# Standard libraries
import re
from datetime import datetime, date, timedelta
from typing import Optional

# Discord
import discord
from discord import app_commands, Embed, Button, ButtonStyle
from discord.ext import commands
import random
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Database
from poyuta.database import User, Quiz, Answer, SessionFactory, initialize_database


# Utils
from poyuta.utils import (
    load_environment,
    process_user_input,
    get_current_quiz,
    get_user_from_id,
    is_admin,
    generate_stats_embed_content,
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

    with bot.session as session:
        if not is_admin(session=session, user=interaction.user):
            await interaction.response.send_message(
                "you are not an admin, you can't use this command"
            )
            return

        latest_quiz = session.query(Quiz).order_by(Quiz.date.desc()).first()

        # get current date
        today = date.today()

        # if the latest quiz date is in the future
        # that means there's already a quiz for today, so add the new date to the planned quizzes
        # i.e latest quiz date + 1 day
        if latest_quiz and latest_quiz.date > today:
            new_date = latest_quiz.date + timedelta(days=1)
        # else there aren't any quiz today, so the new date is today
        else:
            new_date = today

        # add the new quiz to database
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

    with bot.session as session:
        if not is_admin(session=session, user=interaction.user):
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
        if date <= date.today():
            await interaction.response.send_message(
                "You can only update a quiz that hasn't happened yet. Please use a date in the future."
            )
            return

        # check the quiz exists
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
async def male(interaction: discord.Interaction):
    """*Admin only* - Check the planned quizzes."""

    with bot.session as session:
        if not is_admin(session=session, user=interaction.user):
            await interaction.response.send_message(
                "You are not an admin, you can't use this command"
            )
            return

        today = date.today()

        # get all the quizzes that are planned for today or in the future
        quizzes = session.query(Quiz).filter(Quiz.date >= today).all()

        if not quizzes:
            await interaction.response.send_message("No planned quizzes")
            return

        # format the answer
        planned_quizzes = "\n\n".join(
            [
                f"### {quiz.date} :\n \
                - Female : {quiz.female_clip} {quiz.female_answer}\n \
                - Male : {quiz.male_clip} {quiz.male_answer}"
                for quiz in quizzes
            ]
        )
        await interaction.response.send_message(planned_quizzes)

class newquizbutton(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.value = None
    
    @discord.ui.button(label="Guess Male", style=discord.ButtonStyle.green)
    async def postquizresults1(self, interaction: discord.Interaction, button: discord.ui.Button):
        with bot.session as session:
            quiz = get_current_quiz(session=session)
        await interaction.response.send_message(f"**male clip:** {quiz.male_clip}", ephemeral=True)

    @discord.ui.button(label="Guess Female", style=discord.ButtonStyle.green)
    async def postquizresults2(self, interaction: discord.Interaction, button: discord.ui.Button):
        with bot.session as session:
            quiz = get_current_quiz(session=session)
        await interaction.response.send_message(f"**female clip:** {quiz.female_clip}", ephemeral=True)
        

@bot.event
async def post_yesterdays_quiz_results():
    channel_id = config["CHANNEL_ID"]  # Replace with the actual channel ID
    channel = bot.get_channel(channel_id)

    if not channel:
        print("channel not found.")
        return

    # Calculate the date for yesterday
    yesterday = date.today() - timedelta(days=1)

    # Query the database for the quiz that matches the calculated date
    with bot.session as session:
        quiz = session.query(Quiz).filter(Quiz.date == yesterday).first()
        answer = session.query(Answer).filter(Answer.user).first()

    if not quiz:
        print("quiz not found for yesterday.")
        return

    embed = discord.Embed(
        title="Yesterday's Quiz Results",
        color=0xBBE6F3,
    )
    embed.set_author(
        name=config["NEWQUIZ_EMBED_AUTHOR"], icon_url=config["AUTHOR_ICON_URL"]
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

    view = newquizbutton()
    combined_message = await channel.send(embed=embed, view=view)


@bot.command() # for quick debugging
async def postquizresults(ctx):
    await post_yesterdays_quiz_results()


@bot.tree.command(name="female")
@app_commands.describe(seiyuu="guess the female seiyuu")
async def female(interaction: discord.Interaction, seiyuu: str):
    """guess the seiyuu for the current female clip."""

    with bot.session as session:
        quiz = get_current_quiz(session=session)

        if not quiz:
            await interaction.response.send_message("no quiz today :(")

        user = get_user_from_id(
            session=session,
            user_id=interaction.user.id,
            add_if_not_exist=True,
            user_name=interaction.user.name,
        )

    # create the answer object
    user_answer = Answer(
        user_id=user.id,
        quiz_id=quiz.id,
        answer=seiyuu,
        answer_type="female",
    )

    # Generate a pattern to match with the correct answer
    user_answer_pattern = process_user_input(
        seiyuu, partial_match=False, swap_words=True
    )

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

    with bot.session as session:
        quiz = get_current_quiz(session=session)

        if not quiz:
            await interaction.response.send_message("no quiz today :(")

        user = get_user_from_id(
            session=session,
            user_id=interaction.user.id,
            add_if_not_exist=True,
            user_name=interaction.user.name,
        )

    # create the answer object
    user_answer = Answer(
        user_id=user.id,
        quiz_id=quiz.id,
        answer=seiyuu,
        answer_type="male",
    )

    # Generate a pattern to match with the correct answer
    user_answer_pattern = process_user_input(
        seiyuu, partial_match=False, swap_words=True
    )

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


@bot.tree.command(name="mystats")
async def mystats(interaction: discord.Interaction):
    """get your stats."""

    with bot.session as session:
        # get the user
        user = get_user_from_id(
            session=session,
            user_id=interaction.user.id,
            add_if_not_exist=False,
        )

        if not user:
            await interaction.response.send_message("you have not played yet")
            return

        male_answers = [
            answer for answer in user.answers if answer.answer_type == "male"
        ]

        female_answers = [
            answer for answer in user.answers if answer.answer_type == "female"
        ]

        embed = discord.Embed(
            title=f"{user.name}'s Stats",
            color=0xBBE6F3,
        )

        # Get the user's avatar URL
        avatar_url = interaction.user.avatar.url
        embed.set_author(name=interaction.user.name, icon_url=avatar_url)

        # Male Stats
        embed.add_field(name="Male Stats", value="", inline=False)
        embed = generate_stats_embed_content(
            session=session, embed=embed, answers=male_answers
        )

        # Linebreak
        embed.add_field(name="\u200b", value="", inline=False)

        # Female Stats
        embed.add_field(name="Female Stats", value="", inline=False)
        embed = generate_stats_embed_content(
            session=session, embed=embed, answers=female_answers
        )

    await interaction.response.send_message(embed=embed)
