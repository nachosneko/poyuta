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
from poyuta.database import (
    Interaction,
    User,
    Quiz,
    Answer,
    SessionFactory,
    initialize_database,
)


# Utils
from poyuta.utils import (
    load_environment,
    process_user_input,
    get_current_quiz_date,
    get_current_quizzes,
    get_user_from_id,
    is_admin,
    generate_stats_embed_content,
)

config = load_environment()
DAILY_QUIZ_RESET_TIME = datetime.strptime(
    config["DAILY_QUIZ_RESET_TIME"], "%H:%M:%S"
).time()

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
bot = PoyutaBot(command_prefix="?", intents=intents)


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
        post_yesterdays_quiz_results,
        "cron",
        hour=DAILY_QUIZ_RESET_TIME.hour,
        minute=DAILY_QUIZ_RESET_TIME.minute,
        second=DAILY_QUIZ_RESET_TIME.second,
    )
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
                "You are not an admin, you can't use this command."
            )
            return

        latest_quiz = session.query(Quiz).order_by(Quiz.date.desc()).first()

        # get current date
        current_quiz_date = get_current_quiz_date(
            daily_quiz_reset_time=DAILY_QUIZ_RESET_TIME
        )

        # if the latest quiz date is in the future
        # that means there's already a quiz for today, so add the new date to the planned quizzes
        # i.e latest quiz date + 1 day
        if latest_quiz and latest_quiz.date >= current_quiz_date:
            new_date = latest_quiz.date + timedelta(days=1)
        # else there aren't any quiz today, so the new date is today
        else:
            new_date = current_quiz_date

        # add the new quizzes to database
        new_female_quiz = Quiz(
            clip=new_female_clip,
            answer=new_correct_female,
            type="female_seiyuu",
            date=new_date,
        )
        session.add(new_female_quiz)

        new_male_quiz = Quiz(
            clip=new_male_clip,
            answer=new_correct_male,
            type="male_seiyuu",
            date=new_date,
        )
        session.add(new_male_quiz)
        session.commit()

    await interaction.response.send_message(f"New quiz created on {new_date}.")


@bot.tree.command(name="updatequiz")
@app_commands.describe(
    quiz_date="date of the quiz to update in YYYY-MM-DD format",
    quiz_type="type of the quiz to update",
    new_clip="input new clip for female",
    new_answer="input new seiyuu for female clip",
)
async def updatequiz(
    interaction: discord.Interaction,
    quiz_date: str,
    quiz_type: str,
    new_clip: str,
    new_answer: str,
):
    """*Admin only* - Update a planned quiz."""

    with bot.session as session:
        if not is_admin(session=session, user=interaction.user):
            await interaction.response.send_message(
                "You are not an admin, you can't use this command."
            )
            return

        try:
            quiz_date = datetime.strptime(quiz_date, "%Y-%m-%d").date()
        except ValueError:
            await interaction.response.send_message(
                "Invalid date format. Please use YYYY-MM-DD."
            )
            return

        # check the date is in the future
        if quiz_date <= date.today():
            await interaction.response.send_message(
                "You can only update a quiz that hasn't happened yet. Please use a date in the future."
            )
            return

        # check if that quiz exists for this quiz_type and quiz_date
        quiz = (
            session.query(Quiz)
            .filter(Quiz.type == quiz_type, Quiz.date == quiz_date)
            .first()
        )

        if not quiz:
            await interaction.response.send_message(
                f"No {quiz_type} quiz on {quiz_date}. Can't update it."
            )
            return

        # Update attributes
        quiz.clip = new_clip
        quiz.answer = new_answer

        # Commit the changes to the database
        session.commit()

        await interaction.response.send_message(
            f"{quiz_type} quiz updated for {quiz_date}."
        )


@bot.tree.command(name="plannedquizzes")
async def male(interaction: discord.Interaction):
    """*Admin only* - Check the planned quizzes."""

    with bot.session as session:
        if not is_admin(session=session, user=interaction.user):
            await interaction.response.send_message(
                "You are not an admin, you can't use this command."
            )
            return

        current_quiz_date = get_current_quiz_date(
            daily_quiz_reset_time=DAILY_QUIZ_RESET_TIME
        )

        # get all the quizzes that are planned after the current quiz
        unique_date = (
            session.query(Quiz.date)
            .filter(Quiz.date > current_quiz_date)
            .distinct()
            .all()
        )

        if not unique_date:
            await interaction.response.send_message(
                f"No planned quizzes after {current_quiz_date}."
            )
            return

        embed = discord.Embed(title="Planned Quizzes")

        for quiz_date in unique_date:
            quiz_date = quiz_date[0]

            embed.add_field(
                name=f":calendar_spiral: __**{quiz_date}**__", value="", inline=False
            )

            # get female quiz for this date
            quiz = (
                session.query(Quiz)
                .filter(Quiz.type == "female_seiyuu", Quiz.date == quiz_date)
                .first()
            )
            value = (
                f"[{quiz.answer}]({quiz.clip})"
                if quiz
                else "Nothing planned :disappointed_relieved:"
            )
            embed.add_field(
                name=":female_sign: Female",
                value=value,
                inline=True,
            )

            # get male quiz for this date
            quiz = (
                session.query(Quiz)
                .filter(Quiz.type == "male_seiyuu", Quiz.date == quiz_date)
                .first()
            )
            value = (
                f"[{quiz.answer}]({quiz.clip})"
                if quiz
                else "Nothing planned :disappointed_relieved:"
            )
            embed.add_field(
                name=":male_sign: Male",
                value=f"[{quiz.answer}]({quiz.clip})",
                inline=True,
            )

            # Linebreak unless last date
            if quiz_date != unique_date[-1][0]:
                embed.add_field(name="\u200b", value="", inline=False)

        await interaction.response.send_message(embed=embed)


class newquizbutton(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.value = None

    @discord.ui.button(label="Guess Male", style=discord.ButtonStyle.green)
    async def display_male_quiz_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        with bot.session as session:
            current_quiz_date = get_current_quiz_date(
                daily_quiz_reset_time=DAILY_QUIZ_RESET_TIME
            )
            # get male quiz
            current_male_quiz = (
                session.query(Quiz)
                .filter(Quiz.type == "male_seiyuu", Quiz.date == current_quiz_date)
                .first()
            )

        await interaction.response.send_message(
            f"**male clip:** {current_male_quiz.clip}", ephemeral=True
        )

    @discord.ui.button(label="Guess Female", style=discord.ButtonStyle.green)
    async def display_female_quiz_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        with bot.session as session:
            current_quiz_date = get_current_quiz_date(
                daily_quiz_reset_time=DAILY_QUIZ_RESET_TIME
            )
            # get female quiz
            current_female_quiz = (
                session.query(Quiz)
                .filter(Quiz.type == "female_seiyuu", Quiz.date == current_quiz_date)
                .first()
            )
        await interaction.response.send_message(
            f"**female clip:** {current_female_quiz.clip}", ephemeral=True
        )


@bot.event
async def post_yesterdays_quiz_results():
    channel_id = int(config["CHANNEL_ID"])  # Replace with the actual channel ID
    channel = bot.get_channel(channel_id)

    display_new_quiz_buttons = newquizbutton()

    if not channel:
        print("Invalid channel ID.")
        # await channel.send("Invalid channel ID.")
        return

    # Calculate the date for yesterday
    yesterday = get_current_quiz_date(DAILY_QUIZ_RESET_TIME) - timedelta(days=1)

    # Query the database for the quiz that matches the calculated date
    with bot.session as session:
        # check there are quizzes for yesterday
        quiz = session.query(Quiz).filter(Quiz.date == yesterday).first()
        if not quiz:
            embed = discord.Embed(title="There were no quizzes yesterday.")
            await channel.send(embed=embed, view=display_new_quiz_buttons)
            return

        embed = discord.Embed(
            title="Yesterday's Quiz Results",
            color=0xBBE6F3,
        )
        embed.set_author(
            name=config["NEWQUIZ_EMBED_AUTHOR"], icon_url=config["AUTHOR_ICON_URL"]
        )

        # get yesterday's male quiz
        yesterday_male_quiz = (
            session.query(Quiz)
            .filter(Quiz.type == "male_seiyuu", Quiz.date == yesterday)
            .first()
        )
        embed.add_field(
            name="Male", value=f"||{yesterday_male_quiz.answer}||", inline=True
        )
        embed.add_field(name="Clip", value=yesterday_male_quiz.clip, inline=True)

        # Linebreak
        embed.add_field(name="", value="", inline=False)

        # get yesterday's female quiz
        yesterday_female_quiz = (
            session.query(Quiz)
            .filter(Quiz.type == "female_seiyuu", Quiz.date == yesterday)
            .first()
        )
        embed.add_field(
            name="Female", value=f"||{yesterday_female_quiz.answer}||", inline=True
        )
        embed.add_field(name="Clip", value=yesterday_female_quiz.clip, inline=True)

        # Linebreak
        embed.add_field(name="", value="", inline=False)

        # Top Guesseres TODO
        embed.add_field(
            name="Top Guessers",
            value=f"\nTODO\nValue 1 Line 2\nValue 1 Line 3",
            inline=True,
        )

        # TODO
        embed.add_field(name="Time(?)", value="TBA", inline=True)
        embed.add_field(name="Attempts", value="TBA", inline=True)
        embed.add_field(name="Most Guessed (Male)", value="TBA", inline=False)
        embed.add_field(name="Most Guessed (Female)", value="TBA", inline=False)

    await channel.send(embed=embed, view=display_new_quiz_buttons)


@bot.event
async def on_button_click(interaction: discord.Interaction):
    # Check if it's a button interaction
    if isinstance(interaction, discord.ui.Button):
        # Get the user's ID and name
        user_id = interaction.user.id
        user_name = interaction.user.name

        # Get the button label to determine the type of interaction
        button_label = interaction.component.label

        # Store the interaction in the database
        with bot.session as session:
            interaction_entry = Interaction(
                user_id=user_id,
                timestamp=datetime.now(),
                button_label=button_label,
                command_type=None,  # You can set this to "male" or "female" based on the button label
            )
            session.add(interaction_entry)
            session.commit()


@bot.command()  # for quick debugging
async def postquizresults(ctx):
    await post_yesterdays_quiz_results()


@bot.tree.command(name="female_seiyuu")
@app_commands.describe(seiyuu="guess the female seiyuu")
async def female_seiyuu(interaction: discord.Interaction, seiyuu: str):
    """guess the seiyuu for the current female clip."""

    quiz_type = "female_seiyuu"

    with bot.session as session:
        current_quiz_date = get_current_quiz_date(
            daily_quiz_reset_time=DAILY_QUIZ_RESET_TIME
        )

        # get female quiz for this date
        quiz = (
            session.query(Quiz)
            .filter(Quiz.type == quiz_type, Quiz.date == current_quiz_date)
            .first()
        )
        if not quiz:
            await interaction.response.send_message(
                f"No {quiz_type} quiz today :disappointed_relieved:"
            )

        user = get_user_from_id(
            session=session,
            user_id=interaction.user.id,
            add_if_not_exist=True,
            user_name=interaction.user.name,
        )

        # if the user has already answered the quiz correctly
        # don't let them answer again
        for answer in user.answers:
            if answer.quiz_id == quiz.id and answer.is_correct:
                await interaction.response.send_message(
                    f"You have already answered correctly for today's {quiz_type} quiz."
                )
                return

    # create the answer object
    user_answer = Answer(user_id=user.id, quiz_id=quiz.id, answer=seiyuu)

    # Generate a pattern to match with the correct answer
    user_answer_pattern = process_user_input(
        seiyuu, partial_match=False, swap_words=True
    )

    # If the pattern matches : the answer is correct
    if re.search(user_answer_pattern, quiz.answer):
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


@bot.tree.command(name="male_seiyuu")
@app_commands.describe(seiyuu="guess the male seiyuu")
async def male_seiyuu(interaction: discord.Interaction, seiyuu: str):
    """guess the seiyuu for the current male clip."""

    quiz_type = "male_seiyuu"

    with bot.session as session:
        current_quiz_date = get_current_quiz_date(
            daily_quiz_reset_time=DAILY_QUIZ_RESET_TIME
        )

        # get male quiz for this date
        quiz = (
            session.query(Quiz)
            .filter(Quiz.type == quiz_type, Quiz.date == current_quiz_date)
            .first()
        )
        if not quiz:
            await interaction.response.send_message(
                f"No {quiz_type} quiz today :disappointed_relieved:"
            )

        user = get_user_from_id(
            session=session,
            user_id=interaction.user.id,
            add_if_not_exist=True,
            user_name=interaction.user.name,
        )

        # if the user has already answered the quiz correctly
        # don't let them answer again
        for answer in user.answers:
            if answer.quiz_id == quiz.id and answer.is_correct:
                await interaction.response.send_message(
                    f"You have already answered correctly for this today's {quiz_type} quiz."
                )
                return

    # create the answer object
    user_answer = Answer(user_id=user.id, quiz_id=quiz.id, answer=seiyuu)

    # Generate a pattern to match with the correct answer
    user_answer_pattern = process_user_input(
        seiyuu, partial_match=False, swap_words=True
    )

    # If the pattern matches : the answer is correct
    if re.search(user_answer_pattern, quiz.answer):
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
            await interaction.response.send_message("You have not played yet.")
            return

        male_answers = [
            answer for answer in user.answers if answer.quiz.type == "male_seiyuu"
        ]

        female_answers = [
            answer for answer in user.answers if answer.quiz.type == "female_seiyuu"
        ]

        embed = discord.Embed(title="")

        # Get the user's avatar URL
        avatar_url = interaction.user.avatar.url
        embed.set_author(name=interaction.user.name, icon_url=avatar_url)

        # Male Stats
        embed.add_field(name="__**Male Stats**__", value="", inline=False)
        embed = generate_stats_embed_content(
            session=session, embed=embed, answers=male_answers
        )

        # Linebreak
        embed.add_field(name="\u200b", value="", inline=False)

        # Female Stats
        embed.add_field(name="__**Female Stats**__", value="", inline=False)
        embed = generate_stats_embed_content(
            session=session, embed=embed, answers=female_answers
        )

    await interaction.response.send_message(embed=embed)
