# Standard libraries
import re
import random
import numpy as np
from datetime import datetime, date, timedelta, time
from typing import Optional

# Discord
import discord
from discord import app_commands, Embed, Button, ButtonStyle
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler


# Database
from sqlalchemy import case, func
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.session import Session
from poyuta.database import (
    User,
    Quiz,
    QuizType,
    UserStartQuizTimestamp,
    QuizChannels,
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
        value=f"```{config['COMMAND_PREFIX']}male ||my answer||```",
        inline=False,
    )
    embed.add_field(
        name="",
        value=f"```{config['COMMAND_PREFIX']}maleanime ||my answer||```",
        inline=False,
    )
    embed.add_field(
        name="",
        value=f"```{config['COMMAND_PREFIX']}female ||my answer||```",
        inline=False,
    )
    embed.add_field(
        name="",
        value=f"```{config['COMMAND_PREFIX']}femaleanime ||my answer||```",
        inline=False,
    )
    embed.add_field(
        name="",
        value="```/history```",
        inline=False,
    )
    embed.add_field(
        name="", value=f"```{config['COMMAND_PREFIX']}mystats```", inline=False
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
                value="```/updatequiz ```",
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
                    value=f"You have already answered correctly for today's {quiz_type_name} quiz.\nBut you haven't answered the bonus anime point yet. Use `!{quiz_type_name.lower()}anime ||your answer||` to answer it.",
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
                value=f"You haven't started the {quiz_type_name} quiz yet. How would you know the answer? :HMM:",
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

        answer = answer.replace('"', "")
        quiz_answer = quiz.answer.replace('"', "")

        # Generate a pattern to match with the correct answer
        user_answer_pattern = process_user_input(
            input_str=answer, partial_match=False, swap_words=True
        )

        # If the pattern matches: the answer is correct
        if re.search(user_answer_pattern, quiz_answer, re.IGNORECASE):
            # if they don't have a bonus point yet
            if not has_correct_bonus and quiz.bonus_answer:
                bonus_point_feedback = f" (you can also try to get the bonus point using `!{quiz_type_name.lower()}anime ||your answer||`)"
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


# --- Answering anime --- #


@bot.command(name="maleanime", aliases=["ma"])
# Add other decorators as needed
async def male_bonus_answer_quiz(
    ctx: commands.Context,
    *answer: str,
):
    """
    Answer today's male seiyuu bonus anime quiz.
    Please use ||spoiler tags|| to hide your answer.

    Arguments
    ---------
    answer : str
        The answer to the quiz.

    Examples
    ---------
    !maleanime ||your answer||
    !ma ||your answer||
    """

    # edit their message to hide the answer
    await ctx.message.delete()

    # join the answer
    answer = " ".join(answer)

    await answer_bonus_quiz(
        ctx=ctx, quiz_type_id=1, quiz_type_name="Male", answer=answer
    )


@bot.command(name="femaleanime", aliases=["fa"])
# Add other decorators as needed
async def female_bonus_answer_quiz(
    ctx: commands.Context,
    *answer: str,
):
    """
    Answer today's female seiyuu bonus anime quiz.
    Please use ||spoiler tags|| to hide your answer.

    Arguments
    ---------
    answer : str
        The answer to the quiz.

    Examples
    ---------
    !femaleanime ||your answer||
    !fa ||your answer||
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
    """try to get the bonus anime point once you have answered the quiz correctly."""

    answer_time = datetime.now()

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
                value=f"There is no bonus anime point for today's {quiz_type_name} quiz.",
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
                value=f"You have already answered the bonus anime point for today's {quiz_type_name} quiz.",
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

        answer = answer.replace('"', "")
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
                value="❌ Incorrect! Still no bonus anime point for you :disappointed_relieved:",
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
            value=f"> {guess_rate}% ({len(correct_answers)}/{len(played_quizzes)}) + {len(correct_bonus)} correct anime",
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
                f"{medals[i]} | **{answer.answer_time}s** : {answer.answer} in {nb_attempts[i]} attempts on {answer.quiz.date}"
                for i, answer in enumerate(fastest_answers)
            ]
        )

    embed.add_field(
        name="__Fastest guesses__",
        value=fastest_answers,
        inline=True,
    )

    return embed


@bot.command(name="leaderboard", aliases=["lb"])
# Add other decorators as needed
async def leaderboard(ctx: commands.Context):
    """
    Display the leaderboards.

    Score is computed as follows :
    - 1 point for each correct answer
    - 0.5 point for each bonus anime point
    - if there has been more than 5 attempts before getting a correct answer : 0.5 points
    - if there has been more than 8 attempts before getting a correct answer : 0.25 points
    - if there has been more than 3 attempts before getting a correct bonus anime : 0.25 points

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
                value += f"> {rank} <@{id_user}>: {user_scores[quiz_type.type][id_user]} points\n"
            embed.add_field(
                name=f"> {quiz_type.emoji} {quiz_type.type}", value=value, inline=True
            )

        value = ""
        for i, id_user in enumerate(
            list(user_scores["total"].keys())[page_start:page_end]
        ):
            index = page_start + i
            rank = f"{medals[index]} " if index < 3 else f"#{index + 1}: "
            value += f"> {rank} <@{id_user}>: {user_scores['total'][id_user]} points\n"
        embed.add_field(name="> Global Leaderboard", value=value, inline=False)

        pages.append(embed)

    session = EmbedPaginatorSession(ctx, *pages)
    await session.run()


@bot.command(name="seiyuuleaderboard", aliases=["slb"])
# Add other decorators as needed
async def leaderboard(ctx: commands.Context):
    """
    Basically the same leardboard as the main one, except it doesn't take into account the bonus anime points.

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
                value += f"> {rank} <@{id_user}>: {user_scores[quiz_type.type][id_user]} points\n"
            embed.add_field(
                name=f"> {quiz_type.emoji} {quiz_type.type}", value=value, inline=True
            )

        value = ""
        for i, id_user in enumerate(
            list(user_scores["total"].keys())[page_start:page_end]
        ):
            index = page_start + i
            rank = f"{medals[index]} " if index < 3 else f"#{index + 1}: "
            value += f"> {rank} <@{id_user}>: {user_scores['total'][id_user]} points\n"
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

    Score is computed as follows :
    - 1 point for each correct answer
    - 0.5 point for each bonus anime point
    - if there has been more than 5 attempts before getting a correct answer : 0.5 points
    - if there has been more than 8 attempts before getting a correct answer : 0.25 points
    - if there has been more than 3 attempts before getting a correct bonus anime : 0.25 points

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

        # Bonus Anime Points
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
            value += f"> {rank} <@{discord_id}>: {overall} ({male}m + {female}f)\n"

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
                    value=f"There is a bonus anime point for this quiz. Try to get it once you guessed the seiyuu.",
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
    """*Bot Admin only* Force the bot to post yesterday's quiz results."""
    await post_yesterdays_quiz_results()


@commands.check(lambda ctx: is_bot_admin(session=bot.session, user=ctx.author))
@bot.command(aliases=["pqb"])  # for quick debugging
async def postquizbuttons(ctx):
    """*Bot Admin only* Force the bot to post yesterday's quiz results."""
    await post_quiz_buttons()


@bot.tree.command(name="newquiz")
@app_commands.choices(quiz_type=get_quiz_type_choices(session=bot.session))
@app_commands.describe(
    quiz_type="type of the quiz to update",
    new_clip="input new clip",
    new_answer="input new seiyuu",
    new_bonus_answer="The bonus anime answer for the quiz",
)
async def new_quiz(
    interaction: discord.Interaction,
    quiz_type: app_commands.Choice[int],
    new_clip: str,
    new_answer: str,
    new_bonus_answer: Optional[str] = None,
):
    """*Bot Admin only* - create a new quiz."""

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


@bot.tree.command(name="plannedquizzes")
async def planned_quizzes(interaction: discord.Interaction):
    """*Bot Admin only* - Check the planned quizzes."""

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
                    .filter(Quiz.id_type == quiz_type.id, Quiz.date == quiz_date)
                    .first()
                )

                value = (
                    f"[{quiz.answer}]({quiz.clip}){' + ' + quiz.bonus_answer if quiz.bonus_answer else ''}"
                    if quiz
                    else "Nothing planned :disappointed_relieved:"
                )
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


@bot.tree.command(name="updatequiz")
@app_commands.choices(quiz_type=get_quiz_type_choices(session=bot.session))
@app_commands.describe(
    quiz_date="date of the quiz to update in YYYY-MM-DD format",
    quiz_type="type of the quiz to update",
    new_clip="input new clip",
    new_answer="input new seiyuu",
    new_bonus_answer="The bonus anime answer for the quiz (e.g. the anime or the song name)",
)
async def update_quiz(
    interaction: discord.Interaction,
    quiz_date: str,
    quiz_type: app_commands.Choice[int],
    new_clip: str,
    new_answer: str,
    new_bonus_answer: Optional[str] = None,
):
    """*Bot Admin only* - Update a planned quiz."""

    with bot.session as session:
        if not is_bot_admin(session=session, user=interaction.user):
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
        if quiz_date <= get_current_quiz_date(DAILY_QUIZ_RESET_TIME):
            await interaction.response.send_message(
                "You can only update a quiz that hasn't happened yet. Please use a date in the future."
            )
            return

        # check if that quiz exists for this quiz_type and quiz_date
        quiz = (
            session.query(Quiz)
            .filter(Quiz.id_type == quiz_type.value, Quiz.date == quiz_date)
            .first()
        )

        if not quiz:
            await interaction.response.send_message(
                f"No {quiz_type.name} quiz on {quiz_date}. Can't update it."
            )
            return

        # Update attributes
        quiz.clip = new_clip
        quiz.answer = new_answer
        quiz.bonus_answer = new_bonus_answer

        # Commit the changes to the database
        session.commit()

        await interaction.response.send_message(
            f"{quiz_type.name} quiz updated for {quiz_date}."
        )
