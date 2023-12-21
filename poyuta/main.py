# Standard libraries
import re
import random
import numpy as np
from datetime import datetime, date, timedelta, time
from typing import Optional
from typing import List
from collections import defaultdict

# Discord
import discord
from discord import app_commands, Embed, Button, ButtonStyle
from discord.ext import commands
from discord.ext.commands import Context
from apscheduler.schedulers.asyncio import AsyncIOScheduler


# Database
from sqlalchemy import case, func, desc, or_
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.session import Session
from poyuta.database import (
    User,
    Quiz,
    QuizType,
    UserStartQuizTimestamp,
    QuizChannels,
    SubmissionChannels,
    Answer,
    SessionFactory,
    initialize_database,
)

# Utils
from poyuta.paginator import EmbedPaginatorSession
from poyuta.utils import (
    load_environment,
    process_user_input,
    get_current_quiz_date,
    reconstruct_discord_pfp_url,
    get_user,
    get_user_from_id,
    get_quiz_type_choices,
    is_server_admin,
    is_bot_admin,
)

config = load_environment()
DAILY_QUIZ_RESET_TIME = datetime.strptime(
    config["DAILY_QUIZ_RESET_TIME"], "%H:%M:%S"
).time()

intents = discord.Intents.all()
intents.reactions = True
intents.messages = True


initialize_database(
    config["DEFAULT_ADMIN_ID"],
    config["DEFAULT_ADMIN_NAME"],
    True if config["USE_HISTORIC_DATA"] else False,
)


# Update bot class to include the session property
class PoyutaBot(commands.Bot):
    def __init__(self, command_prefix, intents):
        super().__init__(command_prefix=command_prefix, intents=intents)

    # add database session to bot
    # can now be access through bot.session
    @property
    def session(self):
        return SessionFactory()


# Instantiate bot
bot = PoyutaBot(command_prefix=config["COMMAND_PREFIX"], intents=intents)



@bot.event
async def on_ready():
    print(f"logged in as {bot.user.name}")

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        post_yesterdays_quiz_results,
        "cron",
        hour=DAILY_QUIZ_RESET_TIME.hour,
        minute=DAILY_QUIZ_RESET_TIME.minute,
        second=DAILY_QUIZ_RESET_TIME.second,
    )
    scheduler.start()

    print(scheduler.get_jobs())

    try:
        print("syncing commands")
        synced = await bot.tree.sync()
        print(f"synced {len(synced)} command(s)")

        for command in synced:
            print(f"{command.name} synced")
    except Exception as e:
        print(e)

@bot.event
async def on_message(message):
    with bot.session as session:
        submission_channels = session.query(SubmissionChannels).all()

    # Check if the message is in any submission channel
    if message.channel.id in [channel.id_sub_channel for channel in submission_channels]:
        # Delete the message if it's in a submission channel
        await message.delete()
    else:
        # Process other commands if the message is not in a submission channel
        await bot.process_commands(message)

# attempt to decorate up the help command
bot.remove_command("help")


@bot.command()
async def help(ctx, command: str = None):
    # Create an Embed
    embed = discord.Embed(title="Command Help", color=discord.Color.blue())

    embed.add_field(
        name=f"Type `{config['COMMAND_PREFIX']}help <command>` for more details.",
        value="\u200b",
        inline=False,
    )

    # Check if a specific command is requested
    if command:
        # Check if the requested command exists
        command = (
            command.lower()
        )  # Convert to lowercase for case-insensitive comparison

        # Check in general commands
        for cmd in bot.commands:
            if cmd.name.lower() == command:
                # Display the help for the specific command
                embed.add_field(
                    name=f"Help for {config['COMMAND_PREFIX']}{cmd.name}",
                    value=f"{cmd.help}",
                )
                await ctx.send(embed=embed)
                return

        await ctx.send(f"Command `{config['COMMAND_PREFIX']}{command}` not found.")
        return

    # General Commands
    embed.add_field(
        name=f"> **General Commands:**",
        value=f"```{config['COMMAND_PREFIX']}male ||my_answer||```",
        inline=False,
    )
    embed.add_field(
        name="",
        value=f"```{config['COMMAND_PREFIX']}malecharacter ||my_answer||```",
        inline=False,
    )
    embed.add_field(
        name="",
        value=f"```{config['COMMAND_PREFIX']}female ||my_answer||```",
        inline=False,
    )
    embed.add_field(
        name="",
        value=f"```{config['COMMAND_PREFIX']}femalecharacter ||my_answer||```",
        inline=False,
    )
    embed.add_field(
        name="", value=f"```{config['COMMAND_PREFIX']}mystats```", inline=False
    )
    embed.add_field(
        name="", value=f"```{config['COMMAND_PREFIX']}myguesses```", inline=False
    )
    embed.add_field(
        name="", value=f"```{config['COMMAND_PREFIX']}topspeed```", inline=False
    )
    embed.add_field(
        name="", value=f"```{config['COMMAND_PREFIX']}leaderboard```", inline=False
    )
    embed.add_field(
        name="",
        value=f"```{config['COMMAND_PREFIX']}seiyuuleaderboard```",
        inline=False,
    )
    embed.add_field(
        name="",
        value=f"```{config['COMMAND_PREFIX']}legacyleaderboard```",
        inline=False,
    )
    embed.add_field(
        name="",
        value="```/history```",
        inline=False,
    )
    embed.add_field(
        name="",
        value="```/submission```",
        inline=False,
    )
    embed.add_field(
        name="",
        value="```/queue```",
        inline=False,
    )
    with bot.session as session:
        # If the user is an admin, show admin commands
        if is_server_admin(session, ctx.author):
            # Extra spaces
            embed.add_field(name="", value="", inline=False)

            # Server Admin Commands
            embed.add_field(
                name=f"> **Server Admin Commands:**",
                value=f"```{config['COMMAND_PREFIX']}setchannel```",
                inline=False,
            )

            embed.add_field(
                name="",
                value=f"```{config['COMMAND_PREFIX']}unsetchannel```",
                inline=False,
            )

        if is_bot_admin(session, ctx.author):
            # Extra spaces
            embed.add_field(name="", value="", inline=False)

            # Bot Admin Commands (for admins only)
            embed.add_field(
                name=f"> **Bot Admin Commands:**",
                value=f"```{config['COMMAND_PREFIX']}postquizresults```",
                inline=False,
            )

            embed.add_field(
                name="",
                value=f"```{config['COMMAND_PREFIX']}postquizbuttons```",
                inline=False,
            )
            embed.add_field(
                name="",
                value="```/newquiz ```",
                inline=False,
            )
            embed.add_field(
                name="",
                value="```/editquiz ```",
                inline=False,
            )
            embed.add_field(
                name="",
                value="```/editanswer ```",
                inline=False,
            )
            embed.add_field(
                name="",
                value="```/plannedquizzes```",
                inline=False,
            )

    # for c/p new commands: embed.add_field(name="", value="``````", inline=False)

    # Send the embed
    await ctx.send(embed=embed)


# --- Answering seiyuu --- #


@bot.command(name="male", aliases=["m"])
# Add other decorators as needed
async def male_answer_quiz(
    ctx: commands.Context,
    *answer: str,
):
    """
    Answer today's male seiyuu quiz.
    Please use ||spoiler tags|| to hide your answer.

    Arguments
    ---------
    answer : str
        The answer to the quiz.

    Examples
    ---------
    !male ||your answer||
    !m ||your answer||
    """
    # edit their message to hide the answer
    await ctx.message.delete()

    # join the answer
    answer = " ".join(answer)

    await answer_quiz_type(
        ctx=ctx, quiz_type_id=1, quiz_type_name="Male", answer=answer
    )


@bot.command(name="female", aliases=["f"])
# Add other decorators as needed
async def female_answer_quiz(ctx: commands.Context):
    """
    Answer today's female seiyuu quiz.
    Please use ||spoiler tags|| to hide your answer.

    Arguments
    ---------
    answer : str
        The answer to the quiz.

    Examples
    ---------
    !female ||your answer||
    !f ||your answer||
    """

    answer = ctx.message.content.split(" ", 1)[1:]

    # edit their message to hide the answer
    await ctx.message.delete()

    # join the answer
    answer = " ".join(answer)

    await answer_quiz_type(
        ctx=ctx, quiz_type_id=2, quiz_type_name="Female", answer=answer
    )


async def answer_quiz_type(
    ctx: commands.Context,
    quiz_type_id: int,
    quiz_type_name: str,
    answer: str,
):
    """guess the seiyuu for the current quiz_type quiz."""

    answer_time = datetime.now()

    answer = answer.replace('"', "")

    # remove spoiler tags if present
    answer = re.sub(r"\|\|", "", answer)
    answer = answer.strip()

    embed = discord.Embed(
        title=f"{quiz_type_name} Quiz Results",
        color=0xBBE6F3,
    )

    embed.set_author(
        name=ctx.author.name,
        icon_url=ctx.author.avatar.url,
    )

    if not answer:
        embed.add_field(
            name="Invalid",
            value=f"Please provide an answer: `!{quiz_type_name.lower()} ||your answer||`",
            inline=True,
        )

        await ctx.send(embed=embed)
        return

    with bot.session as session:
        current_quiz_date = get_current_quiz_date(
            daily_quiz_reset_time=DAILY_QUIZ_RESET_TIME
        )

        # get quiz for this date and type
        quiz = (
            session.query(Quiz)
            .filter(Quiz.id_type == quiz_type_id, Quiz.date == current_quiz_date)
            .first()
        )
        if not quiz:
            await ctx.send(f"No {quiz_type_name} quiz today :disappointed_relieved:")
            return

        user = get_user(session=session, user=ctx.author, add_if_not_exist=True)

        has_correct_answer = (
            session.query(Answer)
            .filter(
                Answer.user_id == user.id,
                Answer.quiz_id == quiz.id,
                Answer.is_correct,
            )
            .first()
        )
        has_correct_bonus = (
            session.query(Answer)
            .filter(
                Answer.user_id == user.id,
                Answer.quiz_id == quiz.id,
                Answer.is_bonus_point,
            )
            .first()
        )

        # if the user has already answered the quiz correctly
        # don't let them answer again
        if has_correct_answer:
            if quiz.bonus_answer and not has_correct_bonus:
                embed.add_field(
                    name="Invalid",
                    value=f"You have already answered correctly for today's {quiz_type_name} quiz.\nBut you haven't answered the bonus character point yet. Use `!{quiz_type_name.lower()}character ||your answer||` to answer it.",
                    inline=True,
                )

                await ctx.send(embed=embed)
                return

            embed.add_field(
                name="Invalid",
                value=f"You have already answered correctly for today's {quiz_type_name} quiz.",
                inline=True,
            )
            await ctx.send(embed=embed)
            return

        # get the time at which the user clicked the button
        start_quiz_timestamp = (
            session.query(UserStartQuizTimestamp)
            .filter(
                UserStartQuizTimestamp.user_id == user.id,
                UserStartQuizTimestamp.quiz_id == quiz.id,
            )
            .first()
        )

        # if the user hasn't clicked the button yet
        # don't let them answer
        if not start_quiz_timestamp:
            embed.add_field(
                name="Invalid",
                value=f"You haven't started the {quiz_type_name} quiz yet. How would you know the answer? <:worrystare:1184497003267358953>",
                inline=True,
            )

            await ctx.send(embed=embed)
            return

        # compute answer time in seconds
        answer_time = answer_time - start_quiz_timestamp.timestamp
        answer_time = round(answer_time.total_seconds(), 3)

        # create the answer object
        user_answer = Answer(
            user_id=user.id,
            quiz_id=quiz.id,
            answer=answer,
            answer_time=answer_time,
            is_bonus_point=False,
        )

        quiz_answer = quiz.answer.replace('"', "")

        # Generate a pattern to match with the correct answer
        user_answer_pattern = process_user_input(
            input_str=answer, partial_match=False, swap_words=True
        )

        # If the pattern matches: the answer is correct
        if re.search(user_answer_pattern, quiz_answer, re.IGNORECASE):
            # if they don't have a bonus point yet
            if not has_correct_bonus and quiz.bonus_answer:
                bonus_point_feedback = f" (you can also try to get the bonus point using `!{quiz_type_name.lower()}character ||your answer||`)"
            else:
                bonus_point_feedback = ""

            embed.add_field(
                name="Answer",
                value=f"✅ Correct in {answer_time}s!{bonus_point_feedback}",
                inline=True,
            )

            # Store the user's answer in the Answer table
            with bot.session as session:
                user_answer.is_correct = True
                session.add(user_answer)
                session.commit()

            # send the embed
            await ctx.send(embed=embed)

            return

        # Otherwise, the pattern doesn't match: the answer is incorrect
        else:
            embed.add_field(
                name="Answer",
                value="❌ Incorrect!",
                inline=True,
            )

            # Store the user's answer in the Answer table
            with bot.session as session:
                user_answer.is_correct = False
                session.add(user_answer)
                session.commit()

            await ctx.send(embed=embed)

            return


# --- Answering character --- #


@bot.command(name="malecharacter", aliases=["mc", "ma", "maleanime"])
# Add other decorators as needed
async def male_bonus_answer_quiz(
    ctx: commands.Context,
    *answer: str,
):
    """
    Answer today's male seiyuu bonus character quiz.
    Please use ||spoiler tags|| to hide your answer.

    Arguments
    ---------
    answer : str
        The answer to the quiz.

    Examples
    ---------
    !malecharacter ||your answer||
    !ma ||your answer||
    """

    # edit their message to hide the answer
    await ctx.message.delete()

    # join the answer
    answer = " ".join(answer)

    await answer_bonus_quiz(
        ctx=ctx, quiz_type_id=1, quiz_type_name="Male", answer=answer
    )


@bot.command(name="femalecharacter", aliases=["fc", "fa", "femaleanime"])
# Add other decorators as needed
async def female_bonus_answer_quiz(
    ctx: commands.Context,
    *answer: str,
):
    """
    Answer today's female seiyuu bonus character quiz.
    Please use ||spoiler tags|| to hide your answer.

    Arguments
    ---------
    answer : str
        The answer to the quiz.

    Examples
    ---------
    !femalecharacter ||your answer||
    !fc ||your answer||
    """

    # edit their message to hide the answer
    await ctx.message.delete()

    # join the answer
    answer = " ".join(answer)

    await answer_bonus_quiz(
        ctx=ctx, quiz_type_id=2, quiz_type_name="Female", answer=answer
    )


async def answer_bonus_quiz(
    ctx: commands.Context,
    quiz_type_id: int,
    quiz_type_name: str,
    answer: str,
):
    """try to get the bonus character point once you have answered the quiz correctly."""

    answer_time = datetime.now()

    answer = answer.replace('"', "")

    # remove spoiler tags if present
    answer = re.sub(r"\|\|", "", answer)
    answer = answer.strip()

    embed = discord.Embed(
        title=f"{quiz_type_name} Quiz Results",
        color=0xBBE6F3,
    )

    embed.set_author(
        name=ctx.author.name,
        icon_url=ctx.author.avatar.url,
    )

    if not answer:
        embed.add_field(
            name="Invalid",
            value=f"Please provide an answer: `!{quiz_type_name.lower()} ||your answer||`",
            inline=True,
        )

        await ctx.send(embed=embed)
        return

    # check that he answered correctly first
    with bot.session as session:
        current_quiz_date = get_current_quiz_date(
            daily_quiz_reset_time=DAILY_QUIZ_RESET_TIME
        )

        # get quiz for this date and type
        quiz = (
            session.query(Quiz)
            .filter(Quiz.id_type == quiz_type_id, Quiz.date == current_quiz_date)
            .first()
        )
        if not quiz:
            embed.add_field(
                name="Invalid",
                value=f"No {quiz_type_name} quiz today :disappointed_relieved:",
                inline=True,
            )

            await ctx.send(embed=embed)
            return

        # check quiz has a bonus answer
        if not quiz.bonus_answer:
            embed.add_field(
                name="Invalid",
                value=f"There is no bonus character point for today's {quiz_type_name} quiz.",
                inline=True,
            )

            await ctx.send(embed=embed)
            return

        user = get_user(session=session, user=ctx.author, add_if_not_exist=True)

        has_correct_answer = (
            session.query(Answer)
            .filter(
                Answer.user_id == user.id,
                Answer.quiz_id == quiz.id,
                Answer.is_correct,
            )
            .first()
        )
        has_correct_bonus = (
            session.query(Answer)
            .filter(
                Answer.user_id == user.id,
                Answer.quiz_id == quiz.id,
                Answer.is_bonus_point,
            )
            .first()
        )

        if not has_correct_answer:
            embed.add_field(
                name="Invalid",
                value=f"You haven't answered correctly for today's {quiz_type_name} seiyuu quiz.\nUse `!{quiz_type_name.lower()} ||your answer||` to answer before trying out the bonus.",
                inline=True,
            )

            return

        # check that the user hasn't already answered the bonus point
        if has_correct_bonus:
            embed.add_field(
                name="Invalid",
                value=f"You have already answered the bonus character point for today's {quiz_type_name} quiz.",
                inline=True,
            )

            await ctx.send(embed=embed)
            return

        # get the time at which the user clicked the button
        start_quiz_timestamp = (
            session.query(UserStartQuizTimestamp)
            .filter(
                UserStartQuizTimestamp.user_id == user.id,
                UserStartQuizTimestamp.quiz_id == quiz.id,
            )
            .first()
        )

        # compute answer time in seconds
        answer_time = answer_time - start_quiz_timestamp.timestamp
        answer_time = round(answer_time.total_seconds(), 3)

        new_answer = Answer(
            user_id=user.id,
            quiz_id=quiz.id,
            answer="\\Bonus Answer\\",
            bonus_answer=answer,
            answer_time=answer_time,
            is_correct=False,
        )

        quiz_bonus_answer = quiz.bonus_answer.replace('"', "")

        user_bonus_answer_pattern = process_user_input(
            input_str=answer, partial_match=False, swap_words=True
        )

        if re.search(user_bonus_answer_pattern, quiz_bonus_answer, re.IGNORECASE):
            new_answer.is_bonus_point = True
            session.add(new_answer)
            session.commit()

            embed.add_field(
                name="Answer",
                value=f"✅ Correct in {answer_time}s!",
                inline=True,
            )

            await ctx.send(embed=embed)
            return
        else:
            new_answer.is_bonus_point = False
            session.add(new_answer)
            session.commit()

            embed.add_field(
                name="Answer",
                value="❌ Incorrect! Still no bonus character point for you :disappointed_relieved:",
                inline=True,
            )
            await ctx.send(embed=embed)
            return


@bot.command(name="mystats", aliases=["ms", "stats", "s"])
# Add other decorators as needed
async def my_stats(ctx: commands.Context, user_id: Optional[int] = None):
    """
    Get your stats.

    Examples
    ---------
    !mystats
    !ms
    !stats
    !s
    """

    with bot.session as session:
        # get the user

        user = (
            get_user(session=session, user=ctx.author, add_if_not_exist=True)
            if not user_id
            else get_user_from_id(session=session, user_id=user_id)
        )

        if not user:
            await ctx.send(f"{ctx.author.mention} You don't have any stats yet.")
            return

        # create the embed object
        embed = discord.Embed(title="")

        # set the author
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url)

        quiz_types = session.query(QuizType).all()
        for quiz_type in quiz_types:
            embed.add_field(
                name=f"{quiz_type.emoji} {quiz_type.type}", value="", inline=False
            )

            # generate the embed content for this quiz_type
            embed = await generate_stats_embed_content(
                session=session,
                embed=embed,
                user_id=user.id,
                quiz_type=quiz_type,
                daily_quiz_reset_time=DAILY_QUIZ_RESET_TIME,
            )

            # Linebreak unless last quiz type
            if quiz_type != quiz_types[-1]:
                embed.add_field(name="\u200b", value="", inline=False)

    await ctx.send(embed=embed)


async def generate_stats_embed_content(
    session: Session,
    embed: Embed,
    user_id: int,
    quiz_type: Quiz,
    daily_quiz_reset_time: time,
):
    """Generate the stats embed content.

    Parameters
    ----------
    session : Session
        Database session.

    embed : Embed
        Embed to fill.

    answers : list[Answer]
        List of answers to process.

    Returns
    -------
    Embed
        Filled embed.
    """

    current_quiz_date = get_current_quiz_date(daily_quiz_reset_time)

    with session as session:
        # Get the answers for this type

        played_quizzes = (
            session.query(Quiz)
            .join(UserStartQuizTimestamp)
            .filter(
                Quiz.id_type == quiz_type.id,
                UserStartQuizTimestamp.user_id == user_id,
            )
        ).all()

        correct_quizzes = (
            session.query(Quiz)
            .join(Answer)
            .filter(
                Quiz.id_type == quiz_type.id,
                Answer.user_id == user_id,
                Answer.is_correct,
            )
        ).all()

        answers = (
            session.query(Answer)
            .join(Quiz)
            .filter(Answer.user_id == user_id, Quiz.id_type == quiz_type.id)
            .all()
        )

        correct_answers = [answer for answer in answers if answer.is_correct]

        # Guess Rates
        guess_rate = (
            round(len(correct_answers) / len(played_quizzes) * 100, 2)
            if played_quizzes
            else "N/A"
        )
        correct_bonus = [answer for answer in answers if answer.is_bonus_point]
        embed.add_field(
            name="> :dart: Guess Rate",
            value=f"> {guess_rate}% ({len(correct_answers)}/{len(played_quizzes)}) + {len(correct_bonus)} character(s)",
            inline=True,
        )

        # Average Guess Time
        average_guess_time = (
            round(
                np.mean([answer.answer_time for answer in correct_answers]),
                2,
            )
            if correct_answers
            else "N/A"
        )
        embed.add_field(
            name="> :clock1: Average Guess Time",
            value=f"> {average_guess_time}s",
            inline=True,
        )

        embed.add_field(name="", value="", inline=False)

        # Total attempts
        nb_total_attempts = len(
            [
                answer
                for answer in answers
                if answer.answer != "\\Bonus Answer\\"
                and answer.quiz_id in [quiz.id for quiz in correct_quizzes]
            ]
        )

        embed.add_field(
            name="> :1234: Total Attempts",
            value=f"> {nb_total_attempts} attempt(s)",
            inline=True,
        )

        # Average number of attempts per quiz
        average_attempts = (
            round(nb_total_attempts / len(played_quizzes), 2)
            if played_quizzes
            else "N/A"
        )
        embed.add_field(
            name="> :repeat: Average Attempts",
            value=f"> {average_attempts} attempt(s)",
            inline=True,
        )

        embed.add_field(name="", value="", inline=False)

        # Fastest Guesses for this user
        fastest_answers = (
            session.query(Answer)
            .join(Quiz)
            .filter(
                Answer.user_id == user_id,
                Quiz.id_type == quiz_type.id,
                Quiz.date < current_quiz_date,
                Answer.is_correct,
            )
            .order_by(Answer.answer_time)
            .limit(3)
            .all()
        )

        medals = [":first_place:", ":second_place:", ":third_place:"]

        nb_attempts = []
        for fastest_answer in fastest_answers:
            nb_attempts.append(
                session.query(Answer)
                .filter(
                    Answer.user_id == fastest_answer.user_id,
                    Answer.quiz_id == fastest_answer.quiz_id,
                    Answer.answer != "\\Bonus Answer\\",
                )
                .count()
            )

        fastest_answers = "\n\n".join(
            [
                f"{medals[i]} | **{answer.answer_time}s** - {answer.answer} in {nb_attempts[i]} attempts on {answer.quiz.date}"
                for i, answer in enumerate(fastest_answers)
            ]
        )

    embed.add_field(
        name="__Fastest Guesses__",
        value=fastest_answers,
        inline=True,
    )

    return embed

@bot.command(name="myguesses", aliases=["mg", "guesses", "g"])
# Add other decorators as needed
async def my_guesses(ctx: Context, user_id: Optional[int] = None):
    """
    Get your stats.

    Examples
    ---------
    !myguesses
    !mg
    !guesses
    !g
    """

    with bot.session as session:
        # get the user
        user = (
            get_user(session=session, user=ctx.author, add_if_not_exist=True)
            if not user_id
            else get_user_from_id(session=session, user_id=user_id)
        )

        if not user:
            await ctx.send(f"{ctx.author.mention} You don't have any guesses yet.")
            return

        quiz_types = session.query(QuizType).all()
        mgpages = []

        for quiz_type in quiz_types:
            # create the embed object for each quiz type
            embed = discord.Embed(title=f"Top Guesses for {quiz_type.type}")
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url)

            # generate the embed content for this quiz_type
            await generate_guesses_embed_content(
                session=session,
                embed=embed,
                user_id=user.id,
                quiz_type=quiz_type,
                daily_quiz_reset_time=DAILY_QUIZ_RESET_TIME,
                mgpages=mgpages,
                ctx=ctx,  # Pass ctx to the generator
            )

        paginator = EmbedPaginatorSession(ctx, *mgpages)
        await paginator.run()


async def generate_guesses_embed_content(
    session: Session,
    embed: Embed,
    user_id: int,
    quiz_type: Quiz,
    daily_quiz_reset_time: time,
    mgpages: List[Embed],
    ctx: Context,
):
    """Generate the stats embed content.

    Parameters
    ----------
    session : Session
        Database session.

    embed : Embed
        Embed to fill.

    user_id : int
        User ID.

    quiz_type : Quiz
        Quiz type.

    daily_quiz_reset_time : time
        Time of daily quiz reset.

    mgpages : List[Embed]
        List to store pages.

    ctx : Context
        Discord context.

    Returns
    -------
    List[Embed]
        List of filled embeds.
    """

    current_quiz_date = get_current_quiz_date(daily_quiz_reset_time)

    with session as session:
        # Get the answers for this type

        played_quizzes = (
            session.query(Quiz)
            .join(UserStartQuizTimestamp)
            .filter(
                Quiz.id_type == quiz_type.id,
                UserStartQuizTimestamp.user_id == user_id,
            )
        ).all()

        # Correct Quizzes
        correct_quizzes = (
            session.query(Quiz)
            .join(Answer)
            .filter(
                Quiz.id_type == quiz_type.id,
                Answer.user_id == user_id,
                Answer.is_correct,
            )
        ).all()

        # Correct Total
        answers = (
            session.query(Answer)
            .join(Quiz)
            .filter(Answer.user_id == user_id, Quiz.id_type == quiz_type.id)
            .all()
        )

        embed.add_field(name="", value="", inline=False)

        # Fastest Guesses for this user
        fastest_answers = (
            session.query(Answer)
            .join(Quiz)
            .filter(
                Answer.user_id == user_id,
                Quiz.id_type == quiz_type.id,
                Quiz.date < current_quiz_date,
                Answer.is_correct,
            )
            .order_by(Answer.answer_time)
            .all()
        )

        medals = [":first_place:", ":second_place:", ":third_place:"]
        quiz_types = session.query(QuizType).all()
        nb_attempts = []
        for fastest_answer in fastest_answers:
            nb_attempts.append(
                session.query(Answer)
                .filter(
                    Answer.user_id == fastest_answer.user_id,
                    Answer.quiz_id == fastest_answer.quiz_id,
                    Answer.answer != "\\Bonus Answer\\",
                )
                .count()
            )

        for page_start in range(0, len(fastest_answers), 10):
            embed = discord.Embed(title=f"Top Guesses for {quiz_type.type}")
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url)

            page_end = np.min([page_start + 10, len(fastest_answers)])

            for i, answer in enumerate(fastest_answers[page_start:page_end], start=page_start):
                    rank = f"{medals[i % 3]} " if i < 3 else f"#{i + 1} "
                    value = f"{rank} | **{answer.answer_time}s** - {answer.answer} in {nb_attempts[i] if i < len(nb_attempts) else 'Unknown Attempts'} attempt(s) on {answer.quiz.date}"
                    embed.add_field(
                        name=f"", value=value, inline=False
                    )
            mgpages.append(embed)

@bot.command(name="topspeed", aliases=["tops"])
# Add other decorators as needed
async def topspeed(ctx: commands.Context):
    """
    Display the top speed guesses.

    Examples
    ---------
    !topspeed
    !tops
    """

    with bot.session as session:
        answers = session.query(Answer).all()
        medals = [":first_place:", ":second_place:", ":third_place:"]

        if not answers:
            await ctx.send(f"No valid answers found.")
            return

        # Get the fastest answers for this quiz type
        current_quiz_date = get_current_quiz_date(DAILY_QUIZ_RESET_TIME)
        fastest_answers = (
            session.query(Answer)
            .join(Quiz)
            .filter(
                Answer.is_correct,
                Quiz.date < current_quiz_date,
                Answer.answer != "\\Bonus Answer\\",
            )
            .order_by(Answer.answer_time)
            .all()
        )

    toppages = []
    for page_start in range(0, len(fastest_answers), 20):
        embed = discord.Embed(title="Top Speed Guesses")

        page_end = min(page_start + 20, len(fastest_answers))

        for i, answer in enumerate(fastest_answers[page_start:page_end], start=page_start):
            rank = f"{medals[i % 3]} " if i < 3 else f"#{i + 1} "
            value = f"{rank} | **{answer.answer_time}s** - {answer.answer} by <@{answer.user_id}>"
            embed.add_field(
                name=f"", value=value, inline=False
            )
        toppages.append(embed)
    
    session = EmbedPaginatorSession(ctx, *toppages)
    await session.run()




@bot.command(name="currenttop", aliases=["ct"])
async def current_top(ctx: commands.Context):
    """
    Displays today's Top Guesses.

    Examples
    ---------
    !currenttop
    !ct
    """
    with bot.session as session:
        # Get the fastest answers for today's quiz and onwards
        current_quiz_date = get_current_quiz_date(DAILY_QUIZ_RESET_TIME)
        tomorrow_reset_date = current_quiz_date + timedelta(days=1)

        # Explicitly define the join conditions
        fastest_answers = (
            session.query(Answer, QuizType)
            .join(Quiz, Answer.quiz_id == Quiz.id)
            .join(QuizType, Quiz.id_type == QuizType.id)
            .filter(
                Answer.is_correct,
                Quiz.date >= current_quiz_date,
                Quiz.date < tomorrow_reset_date,
                Answer.answer != "\\Bonus Answer\\",
            )
            .order_by(Answer.answer_time)
            .all()
        )

        if not fastest_answers:
            await ctx.send(f"No valid answers found.")
            return

        embed = discord.Embed(title="Today's Top Guesses")

        quiz_types = defaultdict(list)
        medals = [":first_place:", ":second_place:", ":third_place:"]
        for answer, quiz_type in fastest_answers:
            quiz_types[quiz_type.type].append((answer.user.id, answer.answer_time, quiz_type.emoji))

        for quiz_type, user_times in quiz_types.items():
            user_times = sorted(user_times, key=lambda x: x[1])
            
            value = ""
            for i, (user_id, time, emoji) in enumerate(user_times[:10]):
                rank = f"{medals[i]} " if i < 3 else f"#{i + 1}: "
                value += f"> {rank} <@{user_id}> - **{time:.2f}s** \n"

            embed.add_field(name=f"> {emoji} {quiz_type}", value=value, inline=True)

    await ctx.send(embed=embed)

@bot.command(name="leaderboard", aliases=["lb"])
# Add other decorators as needed
async def leaderboard(ctx: commands.Context):
    """
    Display the leaderboards.

    Score is computed as follows:
    - 1 point for each correct answer
    - 0.5 point for each bonus character point
    - if there has been more than 5 attempts before getting a correct answer: 0.5 points
    - if there has been more than 8 attempts before getting a correct answer: 0.25 points
    - if there has been more than 3 attempts before getting a correct bonus character: 0.25 points

    Examples
    ---------
    !leaderboard
    !lb
    """

    with bot.session as session:
        users = session.query(User).all()
        quiz_types = session.query(QuizType).all()
        medals = [":first_place:", ":second_place:", ":third_place:"]

        # initialize the score dict
        user_scores = {"total": {user.id: 0 for user in users}}
        for quiz_type in quiz_types:
            user_scores[quiz_type.type] = {user.id: 0 for user in users}

        for user in users:
            for quiz_type in quiz_types:
                user_score = await compute_user_score(
                    id_user=user.id, id_quiz_type=quiz_type.id
                )
                user_scores[quiz_type.type][user.id] += user_score
                user_scores["total"][user.id] += user_score

        for quiz_type in quiz_types:
            user_scores[quiz_type.type] = await sort_user_scores_by_value(
                user_scores[quiz_type.type]
            )

        # sort global by value
        user_scores["total"] = await sort_user_scores_by_value(user_scores["total"])

    pages = []
    for page_start in range(0, len(users), 10):
        embed = discord.Embed(title="Leaderboard")

        page_end = np.min([page_start + 10, len(users)])

        for quiz_type in quiz_types:
            value = ""
            for i, id_user in enumerate(
                list(user_scores[quiz_type.type].keys())[page_start:page_end]
            ):
                index = page_start + i
                rank = f"{medals[index]} " if index < 3 else f"#{index + 1}: "
                value += f"> {rank} <@{id_user}> - {user_scores[quiz_type.type][id_user]} points\n"
            embed.add_field(
                name=f"> {quiz_type.emoji} {quiz_type.type}", value=value, inline=True
            )

        value = ""
        for i, id_user in enumerate(
            list(user_scores["total"].keys())[page_start:page_end]
        ):
            index = page_start + i
            rank = f"{medals[index]} " if index < 3 else f"#{index + 1}: "
            value += f"> {rank} <@{id_user}> - {user_scores['total'][id_user]} points\n"
        embed.add_field(name="> Global Leaderboard", value=value, inline=False)

        pages.append(embed)

    session = EmbedPaginatorSession(ctx, *pages)
    await session.run()


@bot.command(name="seiyuuleaderboard", aliases=["slb"])
# Add other decorators as needed
async def leaderboard(ctx: commands.Context):
    """
    Basically the same leardboard as the main one, except it doesn't take into account the bonus character points.

    Examples
    ---------
    !seiyuuleaderboard
    !slb
    """

    with bot.session as session:
        users = session.query(User).all()
        quiz_types = session.query(QuizType).all()
        medals = [":first_place:", ":second_place:", ":third_place:"]

        # initialize the score dict
        user_scores = {"total": {user.id: 0 for user in users}}
        for quiz_type in quiz_types:
            user_scores[quiz_type.type] = {user.id: 0 for user in users}

        for user in users:
            for quiz_type in quiz_types:
                user_score = await compute_user_score(
                    id_user=user.id, id_quiz_type=quiz_type.id, bonus_points=False
                )
                user_scores[quiz_type.type][user.id] += user_score
                user_scores["total"][user.id] += user_score

        for quiz_type in quiz_types:
            user_scores[quiz_type.type] = await sort_user_scores_by_value(
                user_scores[quiz_type.type]
            )

        # sort global by value
        user_scores["total"] = await sort_user_scores_by_value(user_scores["total"])

    pages = []
    for page_start in range(0, len(users), 10):
        embed = discord.Embed(title="Leaderboard")

        page_end = np.min([page_start + 10, len(users)])

        for quiz_type in quiz_types:
            value = ""
            for i, id_user in enumerate(
                list(user_scores[quiz_type.type].keys())[page_start:page_end]
            ):
                index = page_start + i
                rank = f"{medals[index]} " if index < 3 else f"#{index + 1}: "
                value += f"> {rank} <@{id_user}> - {user_scores[quiz_type.type][id_user]} points\n"
            embed.add_field(
                name=f"> {quiz_type.emoji} {quiz_type.type}", value=value, inline=True
            )

        value = ""
        for i, id_user in enumerate(
            list(user_scores["total"].keys())[page_start:page_end]
        ):
            index = page_start + i
            rank = f"{medals[index]} " if index < 3 else f"#{index + 1}: "
            value += f"> {rank} <@{id_user}> - {user_scores['total'][id_user]} points\n"
        embed.add_field(name="> Global Leaderboard", value=value, inline=False)

        pages.append(embed)

    session = EmbedPaginatorSession(ctx, *pages)
    await session.run()


async def sort_user_scores_by_value(user_scores: dict):
    return dict(
        sorted(
            user_scores.items(),
            key=lambda item: item[1],
            reverse=True,
        )
    )


async def compute_user_score(
    id_user: int, id_quiz_type: int, bonus_points: bool = True
):
    """
    Compute the score of a user for a given quiz type.

    Score is computed as follows:
    - 1 point for each correct answer
    - 0.5 point for each bonus character point
    - if there has been more than 5 attempts before getting a correct answer: 0.5 points
    - if there has been more than 8 attempts before getting a correct answer: 0.25 points
    - if there has been more than 3 attempts before getting a correct bonus character: 0.25 points

    Parameters
    ----------
    id_user : int
        The id of the user.

    id_quiz_type : int
        The id of the quiz type.

    Returns
    -------
    float
        The score of the user for the given quiz type.
    """

    nb_points = 0
    with bot.session as session:
        # Seiyuu Points
        correct_answers = (
            session.query(Answer)
            .join(Quiz)
            .filter(
                Answer.user_id == id_user,
                Quiz.id_type == id_quiz_type,
                Answer.is_correct,
            )
            .all()
        )

        for answer in correct_answers:
            nb_attempts = (
                session.query(Answer)
                .filter(
                    Answer.user_id == id_user,
                    Answer.quiz_id == answer.quiz_id,
                    Answer.answer != "\\Bonus Answer\\",
                )
                .count()
            )

            nb_point = 1 if nb_attempts <= 5 else 0.5 if nb_attempts <= 8 else 0.25
            nb_points += nb_point

        if not bonus_points:
            return round(float(nb_points), 2)

        # Bonus Character Points
        correct_bonus_answers = (
            session.query(Answer)
            .join(Quiz)
            .filter(
                Answer.user_id == id_user,
                Quiz.id_type == id_quiz_type,
                Answer.is_bonus_point,
            )
            .all()
        )

        for answer in correct_bonus_answers:
            nb_attempts = (
                session.query(Answer)
                .filter(
                    Answer.user_id == id_user,
                    Answer.quiz_id == answer.quiz_id,
                    Answer.answer == "\\Bonus Answer\\",
                )
                .count()
            )

            nb_point = 0.5 if nb_attempts <= 3 else 0.25
            nb_points += nb_point

    return round(float(nb_points), 2)


@bot.command(name="legacyleaderboard", aliases=["llb"])
# Add other decorators as needed
async def legacy_leaderboard(ctx: commands.Context):
    """
    Display the leaderboards for quizzed that happened before this bot.

    Examples
    ---------
    !legacyleaderboard
    !llb
    """

    medals = [":first_place:", ":second_place:", ":third_place:"]

    # open database/legacy_leaderboard.txt and read line by line
    # loop on lines
    # split line on space

    embed = discord.Embed(title="Legacy Leaderboard")

    value = ""
    with open("database/legacy_leaderboard.txt", "r") as file:
        for i, line in enumerate(file):
            if not line:
                continue

            line = line.strip()

            discord_id, male, female, overall = line.split(" ")

            rank = f"{medals[i]} " if i < 3 else f"`#{i + 1}: `"
            value += f"> {rank} <@{discord_id}> - {overall} ({male}m + {female}f)\n"

    embed.add_field(name="> Global Leaderboard", value=value, inline=False)

    await ctx.send(embed=embed)


@bot.tree.command(name="history")
async def history(interaction: discord.Interaction):
    """Get your answer history for today's quiz."""

    with bot.session as session:
        user = get_user(session=session, user=interaction.user, add_if_not_exist=True)

        current_quiz_date = get_current_quiz_date(DAILY_QUIZ_RESET_TIME)

        quiz_types = session.query(QuizType).all()

        embed = discord.Embed(
            title="Today's History",
            color=0xBBE6F3,
        )

        embed.set_author(
            name=interaction.user.name,
            icon_url=interaction.user.avatar.url,
        )

        for quiz_type in quiz_types:
            embed.add_field(
                name=f"> {quiz_type.emoji} {quiz_type.type}",
                value="",
                inline=False,
            )

            # get the answers list for this user and this quiz type
            answers = (
                session.query(Answer)
                .join(Quiz)
                .filter(
                    Answer.user_id == user.id,
                    Quiz.id_type == quiz_type.id,
                    Quiz.date == current_quiz_date,
                )
                .all()
            )

            # if the user hasn't answered yet
            if not answers:
                embed.add_field(
                    name="",
                    value=f"You haven't answered today's {quiz_type.type} quiz yet.",
                    inline=True,
                )

            value = ""
            for answer in answers:
                if answer.answer != "\\Bonus Answer\\":
                    if answer.is_correct:
                        value += f"> ✅ {answer.answer} in {answer.answer_time}s\n"
                    else:
                        value += f"> ❌ {answer.answer} in {answer.answer_time}s\n"
                else:
                    if answer.is_bonus_point:
                        value += f"> ✅ {answer.bonus_answer} in {answer.answer_time}s\n"
                    else:
                        value += f"> ❌ {answer.bonus_answer} in {answer.answer_time}s\n"

            embed.add_field(
                name="",
                value=value,
                inline=True,
            )

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.event
async def post_yesterdays_quiz_results():
    # Calculate the date for yesterday
    current_quiz_date = get_current_quiz_date(DAILY_QUIZ_RESET_TIME)
    yesterday = current_quiz_date - timedelta(days=1)

    # Query the database for the quiz that matches the calculated date
    with bot.session as session:
        quiz_types = session.query(QuizType).all()
        for i, quiz_type in enumerate(quiz_types):
            # get yesterday's male quiz
            yesterday_quiz = (
                session.query(Quiz)
                .filter(Quiz.id_type == quiz_type.id, Quiz.date == yesterday)
                .first()
            )

            embed = discord.Embed(
                title=f"Yesterday's {quiz_type.type} Quiz Results",
                color=0xBBE6F3,
            )

            embed.set_footer(
                text=f"Quiz ID: {yesterday_quiz.id}",
)

            if yesterday_quiz:
                answer_feedback = f"> Answer: ||{yesterday_quiz.answer}||"
                bonus_feedback = (
                    f"\n> Bonus answer: ||{yesterday_quiz.bonus_answer}||"
                    if yesterday_quiz.bonus_answer
                    else ""
                )
                value = f"{answer_feedback}{bonus_feedback}"
            else:
                value = "> No quiz took place :disappointed_relieved:"

            embed.add_field(
                name=f"> {quiz_type.emoji} {quiz_type.type}",
                value=value,
                inline=True,
            )
            embed.add_field(
                name="> Clip",
                value=f"> {yesterday_quiz.clip}" if yesterday_quiz else "> N/A",
                inline=True,
            )

            # if there was no quiz, don't need to send all the stats of the quiz
            # stop the current iteration and go to the next quiz type
            if not yesterday_quiz:
                # send it on every channels set as quiz channel
                for quiz_channel in session.query(QuizChannels).all():
                    channel = bot.get_channel(quiz_channel.id_channel)
                    await channel.send(embed=embed)
                continue

            # if we're here, that means there was a quiz
            creator_pfp = reconstruct_discord_pfp_url(
                user_id=yesterday_quiz.creator_id,
                pfp_hash=yesterday_quiz.creator.pfp,
            )

            embed.set_author(
                name=yesterday_quiz.creator.name,
                icon_url=creator_pfp,
            )

            # Linebreak
            embed.add_field(name="", value="", inline=False)

            # General stats
            nb_seiyuu_attempts = (
                session.query(Answer)
                .filter(
                    Answer.quiz_id == yesterday_quiz.id,
                    Answer.answer != "\\Bonus Answer\\",
                )
                .count()
            )

            nb_correct_seiyuu_answers = (
                session.query(Answer)
                .filter(
                    Answer.quiz_id == yesterday_quiz.id,
                    Answer.answer != "\\Bonus Answer\\",
                    Answer.is_correct,
                )
                .count()
            )

            nb_bonus_attempts = (
                session.query(Answer)
                .filter(
                    Answer.quiz_id == yesterday_quiz.id,
                    Answer.answer == "\\Bonus Answer\\",
                )
                .count()
            )

            nb_correct_bonus_answers = (
                session.query(Answer)
                .filter(
                    Answer.quiz_id == yesterday_quiz.id,
                    Answer.answer == "\\Bonus Answer\\",
                    Answer.is_bonus_point,
                )
                .count()
            )

            embed.add_field(
                name="> :1234: Attempts",
                value=f"> {nb_seiyuu_attempts} attempt(s)",
                inline=True,
            )

            embed.add_field(
                name="> :dart: Points",
                value=f"> {nb_correct_seiyuu_answers} people",
                inline=True,
            )

            # linebreak
            embed.add_field(name="", value="", inline=False)

            embed.add_field(
                name="> :1234: Bonus Attempts",
                value=f"> {nb_bonus_attempts} attempt(s)",
                inline=True,
            )

            embed.add_field(
                name="> :dart: Bonus Points",
                value=f"> {nb_correct_bonus_answers} people",
                inline=True,
            )

            # linebreak
            embed.add_field(name="", value="", inline=False)

            # Top Guessers
            medals = [":first_place:", ":second_place:", ":third_place:"]
            top_faster_answers = (
                session.query(Answer)
                .filter(
                    Answer.quiz_id == yesterday_quiz.id,
                    Answer.is_correct,
                )
                .order_by(Answer.answer_time)
                .limit(3)
                .all()
            )
            top_guessers = "\n".join(
                [
                    f"> {medals[i]} <@{answer.user_id}>"
                    for i, answer in enumerate(top_faster_answers)
                ]
            )
            embed.add_field(
                name="> Top Guessers",
                value=top_guessers,
                inline=True,
            )

            # Times
            top_times = "\n".join(
                [
                    f"> {answer.answer_time}s"
                    for i, answer in enumerate(top_faster_answers)
                ]
            )
            embed.add_field(name="> Time", value=top_times, inline=True)

            # Attempts

            top_attempts = []
            for answer in top_faster_answers:
                user_id = answer.user_id

                nb_attempts = (
                    session.query(Answer)
                    .filter(
                        Answer.quiz_id == yesterday_quiz.id,
                        Answer.user_id == user_id,
                        Answer.answer != "\\Bonus Answer\\",
                    )
                    .count()
                )

                top_attempts.append(f"> {nb_attempts}")

            embed.add_field(
                name="> Attempts", value="\n".join(top_attempts), inline=True
            )

            # Most incorrectly guessed
            # Count each incorrect answer
            incorrect_answers = {}
            for answer in yesterday_quiz.answers:
                if answer.is_correct:
                    continue

                if answer.answer == "\\Bonus Answer\\":
                    continue

                regex_pattern = process_user_input(
                    input_str=answer.answer, partial_match=False, swap_words=True
                )
                for key in incorrect_answers.keys():
                    if re.search(regex_pattern, key, re.IGNORECASE):
                        incorrect_answers[key] += 1
                        break
                else:
                    incorrect_answers[answer.answer] = 1

            # sort the dict by value
            incorrect_answers = dict(
                sorted(
                    incorrect_answers.items(), key=lambda item: item[1], reverse=True
                )
            )

            # top 3 most incorrectly guessed
            top_3_incorrect = "\n".join(
                [
                    f"> {key} ({value} times)"
                    for i, (key, value) in enumerate(incorrect_answers.items())
                    if i < 3
                ]
            )
            embed.add_field(
                name="Most Incorrectly Guessed", value=top_3_incorrect, inline=False
            )

            # Send the message with the view
            # send it on every channels set as quiz channel
            for quiz_channel in session.query(QuizChannels).all():
                channel = bot.get_channel(quiz_channel.id_channel)
                await channel.send(embed=embed)

        for quiz_channel in session.query(QuizChannels).all():
            channel = bot.get_channel(quiz_channel.id_channel)
            view = NewQuizView(current_quiz_date)
            await channel.send(view=view)


@bot.event
async def post_quiz_buttons():
    current_quiz_date = get_current_quiz_date(DAILY_QUIZ_RESET_TIME)
    with bot.session as session:
        for quiz_channel in session.query(QuizChannels).all():
            channel = bot.get_channel(quiz_channel.id_channel)
            view = NewQuizView(current_quiz_date)
            await channel.send(view=view)


class NewQuizButton(discord.ui.Button):
    """Class for the NewQuizButton"""

    def __init__(
        self,
        quiz_type: QuizType,
        new_quiz_date: date,
    ):
        super().__init__(
            label=f"Play today's {quiz_type.type} Quiz",
            style=discord.ButtonStyle.green,
        )

        self.new_quiz_date = new_quiz_date
        self.quiz_type = quiz_type

        # get quiz
        with bot.session as session:
            current_quiz = (
                session.query(Quiz)
                .filter(
                    Quiz.id_type == self.quiz_type.id,
                    Quiz.date == self.new_quiz_date,
                )
                .first()
            )

            self.current_quiz_id = current_quiz.id if current_quiz else None

    async def callback(self, interaction: discord.Interaction):
        if not self.current_quiz_id:
            await interaction.response.send_message(
                f"No {self.quiz_type.type} quiz today :disappointed_relieved:",
                ephemeral=True,
            )
            return

        with bot.session as session:
            current_quiz = session.query(Quiz).get(self.current_quiz_id)

            user = get_user(
                session=session, user=interaction.user, add_if_not_exist=True
            )

            # make sure they didn't click it once already
            if user.id not in [
                start_time.user_id for start_time in current_quiz.start_quiz_timestamps
            ]:
                # Add the timestamp at which they clicked the button in db
                new_start_quiz_timestamp = UserStartQuizTimestamp(
                    user_id=user.id,
                    quiz_id=current_quiz.id,
                    timestamp=datetime.now(),
                )
                session.add(new_start_quiz_timestamp)
                session.commit()

            embed = discord.Embed(
                title=f"{self.quiz_type.emoji} Today's {self.quiz_type.type} Quiz",
                color=0xBBE6F3,
            )

            embed.set_author(
                name=current_quiz.creator.name,
                icon_url=reconstruct_discord_pfp_url(
                    user_id=current_quiz.creator_id, pfp_hash=current_quiz.creator.pfp
                ),
            )

            embed.add_field(
                name="",
                value=current_quiz.clip,
                inline=True,
            )

            if current_quiz.bonus_answer:
                embed.add_field(
                    name="",
                    value=f"There is a bonus character point for this quiz. Try to get it once you guessed the seiyuu.",
                    inline=False,
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)


class NewQuizView(discord.ui.View):
    def __init__(self, new_quiz_date):
        super().__init__(timeout=None)

        with bot.session as session:
            for quiz_type in session.query(QuizType).all():
                button = NewQuizButton(quiz_type=quiz_type, new_quiz_date=new_quiz_date)
                self.add_item(button)


# --- SERVER ADMIN COMMANDS --- #


@commands.check(lambda ctx: is_server_admin(ctx, session=bot.session))
@bot.command(name="setsubmissionchannel", aliases=["ssc"])
async def setsubmissionchannel(ctx):
    """*Server Admin only* - Set the current channel as the submission main channel for this server."""

    with bot.session as session:
        # check if the channel is already set on this server
        submission_channel = session.query(SubmissionChannels).get(ctx.guild.id)

        if submission_channel and submission_channel.id_sub_channel == ctx.channel.id:
            await ctx.send(
                "This channel is already set as the submission channel for this server."
            )
            return

        if submission_channel:
            await ctx.send(
                f"This server already has {bot.get_channel(submission_channel.id_sub_channel).mention} as its channel. Use {config['COMMAND_PREFIX']}unsetchannel to unset it and try again."
            )
            return

        # add the channel to the database
        new_submission_channel = SubmissionChannels(
            id_sub_server=ctx.guild.id, id_sub_channel=ctx.channel.id
        )
        session.add(new_submission_channel)
        session.commit()

    await ctx.send(f"Submission channel set to {ctx.channel.mention}.")


@commands.check(lambda ctx: is_server_admin(ctx, session=bot.session))
@bot.command(name="unsetsubmissionchannel", aliases=["ussc"])
async def unsetsubmissionchannel(ctx):
    """*Server Admin only* - Unset the current channel as the submission channel for this server."""

    with bot.session as session:
        # check if the channel is already set on this server
        submission_channel = session.query(SubmissionChannels).get(ctx.guild.id)

        if not submission_channel:
            await ctx.send(
                f"This server doesn't have a channel set.\nUse {config['COMMAND_PREFIX']}setsubmissionchannel in a channel to set it as the Submission channel."
            )
            return

        # remove the channel from the database
        session.delete(submission_channel)
        session.commit()

    await ctx.send(
        f"Submission channel unset from {bot.get_channel(submission_channel.id_sub_channel).mention}."
    )

@commands.check(lambda ctx: is_server_admin(ctx, session=bot.session))
@bot.command(name="setchannel", aliases=["sc"])
async def setchannel(ctx):
    """*Server Admin only* - Set the current channel as the quiz main channel for this server."""

    with bot.session as session:
        # check if the channel is already set on this server
        quiz_channel = session.query(QuizChannels).get(ctx.guild.id)

        if quiz_channel and quiz_channel.id_channel == ctx.channel.id:
            await ctx.send(
                "This channel is already set as the quiz channel for this server."
            )
            return

        if quiz_channel:
            await ctx.send(
                f"This server already has {bot.get_channel(quiz_channel.id_channel).mention} as its channel. Use {config['COMMAND_PREFIX']}unsetchannel to unset it and try again."
            )
            return

        # add the channel to the database
        new_quiz_channel = QuizChannels(
            id_server=ctx.guild.id, id_channel=ctx.channel.id
        )
        session.add(new_quiz_channel)
        session.commit()

    await ctx.send(f"Quiz channel set to {ctx.channel.mention}.")


@commands.check(lambda ctx: is_server_admin(ctx, session=bot.session))
@bot.command(name="unsetchannel", aliases=["usc"])
async def unsetchannel(ctx):
    """*Server Admin only* - Unset the current channel as the quiz main channel for this server."""

    with bot.session as session:
        # check if the channel is already set on this server
        quiz_channel = session.query(QuizChannels).get(ctx.guild.id)

        if not quiz_channel:
            await ctx.send(
                f"This server doesn't have a channel set.\nUse {config['COMMAND_PREFIX']}setchannel in a channel to set it as the Quiz channel."
            )
            return

        # remove the channel from the database
        session.delete(quiz_channel)
        session.commit()

    await ctx.send(
        f"Quiz channel unset from {bot.get_channel(quiz_channel.id_channel).mention}."
    )


# --- BOT ADMIN COMMANDS --- #


@commands.check(lambda ctx: is_bot_admin(session=bot.session, user=ctx.author))
@bot.command(aliases=["pqr"])  # for quick debugging
async def postquizresults(ctx):
    """**Bot Admin Only** Force the bot to post yesterday's quiz results."""
    await post_yesterdays_quiz_results()


@commands.check(lambda ctx: is_bot_admin(session=bot.session, user=ctx.author))
@bot.command(aliases=["pqb"])  # for quick debugging
async def postquizbuttons(ctx):
    """**Bot Admin Only** Force the bot to post yesterday's quiz results."""
    await post_quiz_buttons()


@bot.tree.command(name="newquiz")
@app_commands.choices(quiz_type=get_quiz_type_choices(session=bot.session))
@app_commands.describe(
    quiz_type="type of the quiz to add",
    new_clip="input new clip",
    new_answer="input new seiyuu",
    new_bonus_answer="The bonus character answer for the quiz",
)
async def new_quiz(
    interaction: discord.Interaction,
    quiz_type: app_commands.Choice[int],
    new_clip: str,
    new_answer: str,
    new_bonus_answer: Optional[str] = None,
):
    """**Bot Admin Only** - create a new quiz."""

    with bot.session as session:
        if not is_bot_admin(session=session, user=interaction.user):
            await interaction.response.send_message(
                "You are not an admin, you can't use this command."
            )
            return

        latest_quiz = (
            session.query(Quiz)
            .filter(Quiz.id_type == quiz_type.value)
            .order_by(Quiz.date.desc())
            .first()
        )

        # get current date
        current_quiz_date = get_current_quiz_date(
            daily_quiz_reset_time=DAILY_QUIZ_RESET_TIME
        )

        # call this just to update pfp
        get_user(session=session, user=interaction.user, add_if_not_exist=True)

        # if the latest quiz date is in the future
        # that means there's already a quiz for today, so add the new date to the planned quizzes
        # i.e latest quiz date + 1 day
        if latest_quiz and latest_quiz.date >= current_quiz_date:
            new_date = latest_quiz.date + timedelta(days=1)
        # else there aren't any quiz today, so the new date is today
        else:
            new_date = current_quiz_date

        # add the new quizzes to database
        new_quiz = Quiz(
            creator_id=interaction.user.id,
            clip=new_clip,
            answer=new_answer,
            bonus_answer=new_bonus_answer,
            id_type=quiz_type.value,
            date=new_date,
        )
        session.add(new_quiz)
        session.commit()

    await interaction.response.send_message(
        f"New {quiz_type.name} quiz created on {new_date}."
    )

@bot.tree.command(name="submission")
@app_commands.choices(quiz_type=get_quiz_type_choices(session=bot.session))
@app_commands.describe(
    quiz_type="type of the quiz to submit",
    clip="mp3 clip",
    answer="correct mp3 answer ",
    bonus_answer="The bonus character answer for the submission",
)
async def send_submission(
    interaction: discord.Interaction,
    quiz_type: app_commands.Choice[int],
    clip: str,
    answer: str,
    bonus_answer: Optional[str] = None,
):
    # Get the server and channel IDs for the current interaction
    server_id = interaction.guild.id
    channel_id = interaction.channel.id

    with bot.session as session:
        # Check if the current channel is allowed for submissions
        submission_channel = (
            session.query(SubmissionChannels)
            .filter_by(id_sub_server=server_id, id_sub_channel=channel_id)
            .first()
        )

        if not submission_channel:
            # If the channel is not allowed, send a message with the correct channel information
            the_correct_channel_to_post_in = (
                session.query(SubmissionChannels.id_sub_channel)
                .filter_by(id_sub_server=server_id)
                .first()
            )

            if the_correct_channel_to_post_in:
                channel_mention = f"<#{the_correct_channel_to_post_in[0]}>"
                await interaction.response.send_message(
                    f"Unauthorized Channel. Please head over to {channel_mention}",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "Unauthorized Channel. Please contact the server administrator.",
                    ephemeral=True,
                )

            return


    with bot.session as session:
        latest_quiz = (
            session.query(Quiz)
            .filter(Quiz.id_type == quiz_type.value)
            .order_by(Quiz.date.desc())
            .first()
        )

        # get current date
        current_quiz_date = get_current_quiz_date(
            daily_quiz_reset_time=DAILY_QUIZ_RESET_TIME
        )

        # call this just to update pfp
        get_user(session=session, user=interaction.user, add_if_not_exist=True)

        # if the latest quiz date is in the future
        # that means there's already a quiz for today, so add the new date to the planned quizzes
        # i.e latest quiz date + 1 day
        if latest_quiz and latest_quiz.date >= current_quiz_date:
            new_date = latest_quiz.date + timedelta(days=1)
        # else there aren't any quiz today, so the new date is today
        else:
            new_date = current_quiz_date

        # add the new quizzes to database
        new_quiz = Quiz(
            creator_id=interaction.user.id,
            clip=clip,
            answer=answer,
            bonus_answer=bonus_answer,
            id_type=quiz_type.value,
            date=new_date,
        )
        session.add(new_quiz)
        session.commit()
    await interaction.response.send_message("✅")
    # Send the result as a direct message to the user
    await interaction.user.send(f"Submission for {quiz_type.name} added for {new_date}\n ||[{answer}]({clip})|| {'+ ||' + bonus_answer if bonus_answer else ''}||")

@bot.tree.command(name="plannedquizzes")
async def planned_quizzes(interaction: discord.Interaction):
    """**Bot Admin Only** - Check the planned quizzes."""

    with bot.session as session:
        if not is_bot_admin(session=session, user=interaction.user):
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
            .filter(Quiz.date >= current_quiz_date)
            .distinct()
            .all()
        )

        if not unique_date:
            await interaction.response.send_message(
                f"No planned quizzes after {current_quiz_date}."
            )
            return

        embed = discord.Embed(title="Planned Quizzes")

        # get all the quiz types
        quiz_types = session.query(QuizType).all()

        for i, quiz_date in enumerate(unique_date):
            quiz_date = quiz_date[0]

            embed.add_field(
                name=f":calendar_spiral: __**{quiz_date if i != 0 else 'Today'}**__",
                value="",
                inline=False,
            )

            for i, quiz_type in enumerate(quiz_types):
                # get quiz for this type and date
                quiz = (
                    session.query(Quiz)
                    .filter(Quiz.id_type == quiz_type.id, Quiz.date == quiz_date, Quiz.creator_id)
                    .first()
                )

                if quiz:
                    creator_id = quiz.creator_id
                    value = (
                        f"||[{quiz.answer}]({quiz.clip})||{' + ||' + quiz.bonus_answer if quiz.bonus_answer else ''}|| by <@{creator_id}>"
                    )
                else:
                    value = "Nothing planned :disappointed_relieved:"

                embed.add_field(
                    name=f"> {quiz_type.emoji} {quiz_type.type}",
                    value=f"> {value}",
                    inline=True,
                )

                # Linebreak every two types unless last type
                if i % 2 == 0 and i != 0 and i != len(quiz_types) - 1:
                    embed.add_field(name="", value="", inline=False)

            # Linebreak unless last date
            if quiz_date != unique_date[-1][0]:
                embed.add_field(name="\u200b", value="", inline=False)

        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="queue")
async def queue(interaction: discord.Interaction):
    """Check the planned quizzes."""

    with bot.session as session:
        current_quiz_date = get_current_quiz_date(
            daily_quiz_reset_time=DAILY_QUIZ_RESET_TIME
        )

        # get all the quizzes that are planned after the current quiz
        unique_date = (
            session.query(Quiz.date)
            .filter(Quiz.date >= current_quiz_date)
            .distinct()
            .all()
        )

        if not unique_date:
            await interaction.response.send_message(
                f"No planned quizzes after {current_quiz_date}."
            )
            return

        embed = discord.Embed(title="Planned Quizzes")

        # get all the quiz types
        quiz_types = session.query(QuizType).all()

        for i, quiz_date in enumerate(unique_date):
            quiz_date = quiz_date[0]

            embed.add_field(
                name=f":calendar_spiral: __**{quiz_date if i != 0 else 'Today'}**__",
                value="",
                inline=False,
            )

            for i, quiz_type in enumerate(quiz_types):
                # get quiz for this type and date
                quiz = (
                    session.query(Quiz)
                    .filter(Quiz.id_type == quiz_type.id, Quiz.date == quiz_date)
                    .first()
                )

                if quiz:
                    creator_id = quiz.creator_id
                    value = (
                        f"Queued by <@{creator_id}>"
                    )
                else:
                    value = "Nothing planned :disappointed_relieved:"

                embed.add_field(
                    name=f"> {quiz_type.emoji} {quiz_type.type}",
                    value=f"> {value}",
                    inline=True,
                )

                # Linebreak every two types unless last type
                if i % 2 == 0 and i != 0 and i != len(quiz_types) - 1:
                    embed.add_field(name="", value="", inline=False)

            # Linebreak unless last date
            if quiz_date != unique_date[-1][0]:
                embed.add_field(name="\u200b", value="", inline=False)

        await interaction.response.send_message(embed=embed)


@bot.tree.command(name="editquiz")
@app_commands.choices(quiz_type=get_quiz_type_choices(session=bot.session))
@app_commands.describe(
    quiz_date="date of the quiz to update in YYYY-MM-DD format",
    quiz_type="type of the quiz to update",
    new_clip="input new clip",
    new_answer="input new seiyuu",
    new_bonus_answer="the bonus character answer for the quiz.",
    clear_button_clicks="clears everyone's button clicks for the selected quiz type. only use if the clip link is broken for everyone.",
    clear_attempts="clears everyone's attempts for the selected quiz type. only use if you want to change the seiyuu clip and answer altogether.",
    delete_quiz="delete the quiz for targetted date.",
)
async def edit_quiz(
    interaction: discord.Interaction,
    quiz_date: str,
    quiz_type: app_commands.Choice[int],
    new_clip: Optional[str] = None,
    new_answer: Optional[str] = None,
    new_bonus_answer: Optional[str] = None,
    clear_button_clicks: Optional[bool] = False,
    clear_attempts: Optional[bool] = False,
    delete_quiz: Optional[bool] = False,
):
    """**Bot Admin Only** - Update a planned quiz."""

    with bot.session as session:
        # Check if the user is an admin
        is_admin = is_bot_admin(session=session, user=interaction.user)

        # Check if the quiz exists for this quiz_type and quiz_date
        quiz = (
            session.query(Quiz)
            .filter(Quiz.id_type == quiz_type.value, Quiz.date == quiz_date)
            .first()
        )

        if not quiz:
            try:
                quiz_date = datetime.strptime(quiz_date, "%Y-%m-%d").date()
            except ValueError:
                await interaction.response.send_message(
                "invalid date format. please use YYYY-MM-DD."
            )
            return

        # Check if the user is the creator of the quiz or an admin
        if not is_admin and quiz.creator_id != interaction.user.id:
            await interaction.response.send_message(
                "You are not authorized to edit or delete this quiz."
            )
            return

        if delete_quiz:
            if quiz:
                # Delete the quiz
                session.delete(quiz)

                # Commit the deletion to the database
                session.commit()

                await interaction.response.send_message(
                    f"{quiz_type.name} quiz for {quiz_date} deleted."
                )
            else:
                await interaction.response.send_message(
                    f"no {quiz_type.name} quiz on {quiz_date}."
                )
            return

        if clear_button_clicks:
            # Conditionally delete rows from UserStartQuizTimestamp based on gender
            gender_condition = (
                UserStartQuizTimestamp.timestamp
                if quiz_type.value == 1  # 1 represents male and 2 represents female
                else desc(UserStartQuizTimestamp.timestamp)
            )

            latest_timestamps = (
                session.query(UserStartQuizTimestamp)
                .filter_by(quiz_id=quiz.id)
                .order_by(gender_condition)
                .all()
            )

            if latest_timestamps:
                session.query(UserStartQuizTimestamp).filter(UserStartQuizTimestamp.quiz_id == quiz.id).delete()

                # Commit the deletion to the database
                session.commit()

                await interaction.response.send_message(
                    f"{quiz_type.name} quiz updated for {quiz_date}. "
                    f"buttons for {quiz_type.name} also resetted."
                )
            else:
                await interaction.response.send_message(
                    "nothing to clear."
                )
        if clear_attempts:
            # Conditionally delete rows from Answer based on quiz type
            # Separate conditions for male and female quiz types
            gender_condition_answer = (
                Answer.quiz_id
                if quiz.type.id == 1  # 1 represents Male Seiyuu and 2 represents Female Seiyuu
                else desc(Answer.quiz_id)
            )

            latest_answer = (
                session.query(Answer)
                .filter_by(quiz_id=quiz.id)
                .order_by(gender_condition_answer)
                .limit(1)
                .first()
            )

            if latest_answer:
                # Filter and delete rows based on quiz type condition
                session.query(Answer).filter(
                    Answer.quiz_id == quiz.id,
                    Answer.quiz.has(Quiz.id_type == quiz.type.id),
                    Answer.quiz.has(Quiz.date == quiz.date),

                ).delete()

                # Commit the deletion to the database
                session.commit()

                await interaction.response.send_message(
                    f"{quiz.type.type} quiz updated for {quiz.date}. "
                    f"{quiz.type.type} attempts for today cleared."
                )
            else:
                await interaction.response.send_message(
                    f"{quiz.type.type} quiz updated for {quiz.date}. "
                    f"no {quiz.type.type} attempts made today."
                )

        else:
            # If none of the special options were selected, proceed with regular updates
            if any([new_clip, new_answer, new_bonus_answer]):
                # Update attributes
                quiz.clip = new_clip if new_clip is not None else quiz.clip
                quiz.answer = new_answer if new_answer is not None else quiz.answer
                quiz.bonus_answer = (
                    new_bonus_answer if new_bonus_answer is not None else quiz.bonus_answer
                )

                # Commit the changes to the database
                session.commit()

                await interaction.response.send_message(
                    f"{quiz_type.name} quiz updated for {quiz_date}."
                )
            else:
                await interaction.response.send_message(
                    "please provide one or more of the optional values to update."
                )

# Command to edit answers
@bot.tree.command(name="editanswer")
@app_commands.describe(
    user_id="which user to edit",
    answer="which answer to edit",
    answer_time="which answer time to edit",
    new_answer="new answer",
    new_answer_time="time to edit",
    is_correct="is correct or not",
    delete="delete the attempt",
)
async def edit_answer(
    interaction: discord.Interaction,
    user_id: str,
    answer: str,
    answer_time: str,
    new_answer: Optional[str] = None,
    new_answer_time: Optional[str] = None,
    is_correct: Optional[bool] = None,
    delete: Optional[bool] = False,
):
    """**Bot Admin Only** - edit or delete an answer and/or time."""
    
    # Check if the user invoking the command is an admin
    with bot.session as session:
        if not is_bot_admin(session=session, user=interaction.user):
            await interaction.response.send_message(
                "You are not an admin, you can't use this command."
            )
            return
    
    # Access the database
    with SessionFactory() as session:
        # Retrieve the answer to be edited or deleted based on user_id, answer, and answer_time
        answer_obj = (
            session.query(Answer)
            .filter_by(user_id=user_id, answer=answer, answer_time=answer_time)
            .first()
        )
        
        # Get the user
        user = (
            get_user(session=session, user=interaction.author, add_if_not_exist=True)
            if not user_id
            else get_user_from_id(session=session, user_id=user_id)
        )
        if not user:
            await interaction.send(f"{interaction.author.mention} This person doesn't have any guesses yet.")
            return
        
        # Check if the result is None
        if answer_obj is None:
            await interaction.response.send_message("Answer not found.")
            return

        # Delete the answer if delete is True
        if delete:
            session.delete(answer_obj)
            session.commit()
            await interaction.response.send_message(f"Answer for user **{user.name}**, answer {answer}, and time {answer_time} deleted.")
            return

        # Update the answer if new_answer is provided
        if new_answer is not None:
            answer_obj.answer = new_answer

        # Update other optional fields
        if new_answer_time is not None:
            answer_obj.answer_time = float(new_answer_time)
        if is_correct is not None:
            answer_obj.is_correct = is_correct

        session.commit()

        await interaction.response.send_message(f"Answer for user **{user.name}**, answer {answer}, and time {answer_time} updated.")

# Helper function to check if a user is an admin
def is_bot_admin(session, user):
    try:
        user_obj = session.query(User).filter_by(id=user.id, is_admin=True).first()
        return user_obj is not None
    except Exception as e:
        return False
