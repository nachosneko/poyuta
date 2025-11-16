

# Standard libraries
import re
import os
import shutil
import random
import asyncio
import sqlite3
import numpy as np
from datetime import datetime, date, timedelta, time
from typing import Optional
from typing import List
from collections import OrderedDict
from itertools import islice
from difflib import SequenceMatcher

# Discord
import discord
from discord import app_commands, Embed, Button, ButtonStyle
from discord.ui import View, Button
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

class PoyutaBot(commands.Bot):
    def __init__(self, command_prefix, intents):
        super().__init__(command_prefix=command_prefix, intents=intents)
        self.last_leaderboard_update = None
        self.last_leaderboard_message = None

    @property
    def session(self):
        return SessionFactory()

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
    if message.channel.id in [
        channel.id_sub_channel for channel in submission_channels
    ]:
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
    embed = discord.Embed(title="General Command Help #1", color=discord.Color.blue())

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

    pages = []

    # General commands list
    general_commands = [
        (f"{config['COMMAND_PREFIX']}mc ||my_answer||"),
        (f"{config['COMMAND_PREFIX']}mcb ||my_answer||"),
        (f"{config['COMMAND_PREFIX']}fc ||my_answer||"),
        (f"{config['COMMAND_PREFIX']}fcb ||my_answer||"),
        (f"{config['COMMAND_PREFIX']}fc2 ||my_answer||"),
        (f"{config['COMMAND_PREFIX']}fc2b ||my_answer||"),
        (f"{config['COMMAND_PREFIX']}s ||my_answer||"),
        (f"{config['COMMAND_PREFIX']}sb ||my_answer||"),
        (f"{config['COMMAND_PREFIX']}s2 ||my_answer||"),
        (f"{config['COMMAND_PREFIX']}s2b ||my_answer||"),
        (f"{config['COMMAND_PREFIX']}mystats"),
        (f"{config['COMMAND_PREFIX']}mcg"),
        (f"{config['COMMAND_PREFIX']}fcg"),
        (f"{config['COMMAND_PREFIX']}fc2g"),
        (f"{config['COMMAND_PREFIX']}sg"),
        (f"{config['COMMAND_PREFIX']}s2g"),
        (f"{config['COMMAND_PREFIX']}leaderboard"),
        (f"{config['COMMAND_PREFIX']}nobonusleaderboard"),
        (f"{config['COMMAND_PREFIX']}legacyleaderboard"),
        ("/ct"),
        ("/log"),
        ("/sss"),
        ("/qq"),
    ]

    admin_commands = [
        (f"{config['COMMAND_PREFIX']}postquizresults"),
        (f"{config['COMMAND_PREFIX']}postquizbuttons"),
        ("/nq"),
        ("/equiz"),
        ("/eanswer"),
        ("/pq"),
    ]

    per_page = 10
    for i, command in enumerate(general_commands):
        embed.add_field(name="", value=f"```{command}```", inline=False)

        # not the first or last command
        if (i + 1) % per_page == 0 and i != 0 and i != len(general_commands) - 1:
            pages.append(embed)
            embed = discord.Embed(
                title=f"General Command Help #{len(pages)+1}",
                color=discord.Color.blue(),
            )
            embed.add_field(
                name=f"Type `{config['COMMAND_PREFIX']}help <command>` for more details.",
                value="\u200b",
                inline=False,
            )

    pages.append(embed)

    # Check admin status
    with bot.session as session:
        if is_bot_admin(session, ctx.author):

            embed = discord.Embed(title="Admin Command Help", color=discord.Color.red())

            # Create an embed for each admin command
            for command in admin_commands:
                embed.add_field(name="", value=f"```{command}```", inline=False)

            pages.append(embed)

    session = EmbedPaginatorSession(ctx, *pages)

    # Send the embed
    await session.run()

# --- Slash Answers --- #

QUIZ_TYPES = {
    "malecharacter": 1, "mc": 1,
    "femalecharacter": 2, "fc": 2,
    "femalecharacter2": 3, "fc2": 3,
    "song": 4, "s": 4,
    "song2": 5, "s2": 5,
}

QUIZ_TYPE_TITLES = {
    "mc": "Male Character Quiz",
    "malecharacter": "Male Character Quiz",
    "fc": "Female Character Quiz",
    "femalecharacter": "Female Character Quiz",
    "fc2": "Female Character 2 Quiz",
    "femalecharacter2": "Female Character 2 Quiz",
    "song": "Song Quiz",
    "s": "Song Quiz",
    "song2": "Song 2 Quiz",
    "s2": "Song 2 Quiz",
}

class PostResultView(discord.ui.View):
    def __init__(self, embed: discord.Embed, user: discord.User):
        super().__init__(timeout=None) 
        self.embed = embed
        self.user = user

    @discord.ui.button(label="Post it in public", style=discord.ButtonStyle.blurple)
    async def post_button(self, interaction: discord.Interaction, button: discord.ui.Button):


        await interaction.channel.send(embed=self.embed)

async def answer_quiz_slash(
    interaction: discord.Interaction, 
    quiz_type_name: str, 
    answer: str
):
    """Universal handler for slash commands (main + bonus answers) with duplicate prevention."""
    answer_time = datetime.now()

    # Clean and normalize input
    answer = re.sub(r"\|\|", "", answer).strip()
    
    embed = discord.Embed(
        title=f"{QUIZ_TYPE_TITLES.get(quiz_type_name.lower(), quiz_type_name.capitalize())} Results",
        color=0xBBE6F3,
    )
    embed.set_author(name=interaction.user.name, icon_url=interaction.user.avatar.url)

    if not answer:
        embed.add_field(name="Invalid", value=f"Please provide an answer.", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    with bot.session as session:
        quiz_type_id = QUIZ_TYPES[quiz_type_name.lower()]
        current_quiz_date = get_current_quiz_date(DAILY_QUIZ_RESET_TIME)
        quiz = session.query(Quiz).filter_by(id_type=quiz_type_id, date=current_quiz_date).first()

        if not quiz:
            await interaction.response.send_message(
                f"No {quiz_type_name} quiz today :disappointed_relieved:", ephemeral=True
            )
            return

        user = get_user(session=session, user=interaction.user, add_if_not_exist=True)

        # Fetch user answer records
        has_correct_answer = session.query(Answer).filter_by(
            user_id=user.id, quiz_id=quiz.id, is_correct=True
        ).first()
        has_correct_bonus = session.query(Answer).filter_by(
            user_id=user.id, quiz_id=quiz.id, is_bonus_point=True
        ).first()

        # Make sure the quiz was started
        start_quiz_timestamp = session.query(UserStartQuizTimestamp).filter_by(
            user_id=user.id, quiz_id=quiz.id
        ).first()
        if not start_quiz_timestamp:
            embed.add_field(
                name="Invalid",
                value=f"You haven't started the {quiz_type_name} quiz yet.",
                inline=True,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Calculate time spent
        answer_duration = answer_time - start_quiz_timestamp.timestamp
        answer_duration_sec = round(answer_duration.total_seconds(), 3)

        # Helper function for duplicate detection
        def is_duplicate_attempt(previous: str, current: str) -> bool:
            """Check if two answers are duplicates, considering regex, casing, and word swaps."""
            if not previous or not current:
                return False

            # Compile regex pattern using your vowel/length rules + swap handling
            pattern = process_user_input(previous, partial_match=False, swap_words=True)
            return re.fullmatch(pattern, current, re.IGNORECASE) is not None

        # --- MAIN QUIZ ANSWER PHASE ---
        if not has_correct_answer:
            quiz_answers = quiz.answer.split("|")
            user_answer_pattern = process_user_input(answer, False, True)

            # ✅ Check if user already tried same incorrect main answer before
            all_previous = session.query(Answer).filter_by(
                user_id=user.id,
                quiz_id=quiz.id,
                is_bonus_point=False,
                is_correct=False
            ).all()

            attempted_before = any(is_duplicate_attempt(prev.answer, answer) for prev in all_previous)

            if attempted_before:
                embed.add_field(
                    name="Duplicate Attempt",
                    value="⚠️ You've already tried that answer.",
                    inline=True
                )
                view = PostResultView(embed, interaction.user)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

                return

            # --- Correctness Check ---
            is_correct = any(
                re.search(user_answer_pattern, a.strip(), re.IGNORECASE)
                for a in quiz_answers
            )

            similarities = [
                SequenceMatcher(None, answer.lower(), a.lower().strip()).ratio()
                for a in quiz_answers
            ]
            similarity_percentage = round(max(similarities) * 100, 2) if similarities else 0

            # --- Record Attempt ---
            user_answer = Answer(
                user_id=user.id,
                quiz_id=quiz.id,
                answer=answer.strip(),
                answer_time=answer_duration_sec,
                is_bonus_point=False,
                is_correct=is_correct,
            )

            if is_correct:
                msg = f"✅ Correct in {answer_duration_sec}s!"
                if quiz.bonus_answer:
                    msg += f" (you can also try to get the bonus point using the same slash command)"
            else:
                close_feedback = f" ({similarity_percentage}%)" if similarity_percentage >= 75 else ""
                msg = f"❌ Incorrect in {answer_duration_sec}s{close_feedback}"

            embed.add_field(name="Answer", value=msg, inline=True)
            session.add(user_answer)
            session.commit()
            view = PostResultView(embed, interaction.user)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

            return

        # --- BONUS ANSWER PHASE ---
        elif quiz.bonus_answer and not has_correct_bonus:
            quiz_bonus_answers = quiz.bonus_answer.split("|")
            user_bonus_pattern = process_user_input(answer, False, True)

            # ✅ Check if user already tried same incorrect bonus before
            all_previous_bonus = session.query(Answer).filter_by(
                user_id=user.id,
                quiz_id=quiz.id,
                is_bonus_point=False,
                is_correct=False
            ).all()

            attempted_before_bonus = any(
                is_duplicate_attempt(prev.bonus_answer or prev.answer, answer)
                for prev in all_previous_bonus
            )

            if attempted_before_bonus:
                embed.add_field(
                    name="Duplicate Attempt",
                    value="⚠️ You've already tried that answer.",
                    inline=True
                )
                view = PostResultView(embed, interaction.user)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                return

            # --- Correctness Check ---
            is_bonus_correct = any(
                re.search(user_bonus_pattern, a.strip(), re.IGNORECASE)
                for a in quiz_bonus_answers
            )

            similarities = [
                SequenceMatcher(None, answer.lower(), a.lower().strip()).ratio()
                for a in quiz_bonus_answers
            ]
            similarity_percentage = round(max(similarities) * 100, 2) if similarities else 0

            # --- Record Bonus Attempt ---
            bonus_entry = Answer(
                user_id=user.id,
                quiz_id=quiz.id,
                answer="\\Bonus Answer\\",
                bonus_answer=answer,
                answer_time=answer_duration_sec,
                is_correct=False,
                is_bonus_point=is_bonus_correct,  # only True when correct
            )

            session.add(bonus_entry)
            session.commit()

            # --- Feedback ---
            if is_bonus_correct:
                embed.add_field(
                    name="Bonus Answer",
                    value=f"✅ Correct bonus in {answer_duration_sec}s!",
                    inline=True,
                )
            else:
                close_feedback = f" ({similarity_percentage}%)" if similarity_percentage >= 75 else ""
                embed.add_field(
                    name="Bonus Answer",
                    value=f"❌ Incorrect bonus in {answer_duration_sec}s{close_feedback}",
                    inline=True,
                )

            view = PostResultView(embed, interaction.user)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

            return

        # --- ALREADY DONE ---
        else:
            embed.add_field(
                name="Already Completed",
                value=f"You’ve already answered and claimed today’s {quiz_type_name} quiz and bonus.",
                inline=True,
            )
            view = PostResultView(embed, interaction.user)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            return

# --- Slash Commands for Each Quiz Type ---
@bot.tree.command(name="mc")
@app_commands.describe(answer="Your answer to today's male character quiz")
async def malecharacter(interaction: discord.Interaction, answer: str):
    await answer_quiz_slash(interaction, "mc", answer)

@bot.tree.command(name="fc")
@app_commands.describe(answer="Your answer to today's female character quiz")
async def femalecharacter(interaction: discord.Interaction, answer: str):
    await answer_quiz_slash(interaction, "fc", answer)

@bot.tree.command(name="fc2")
@app_commands.describe(answer="Your answer to today's female character 2 quiz")
async def femalecharacter2(interaction: discord.Interaction, answer: str):
    await answer_quiz_slash(interaction, "fc2", answer)

@bot.tree.command(name="song")
@app_commands.describe(answer="Your answer to today's song quiz")
async def song(interaction: discord.Interaction, answer: str):
    await answer_quiz_slash(interaction, "song", answer)

@bot.tree.command(name="song2")
@app_commands.describe(answer="Your answer to today's song 2 quiz")
async def song2(interaction: discord.Interaction, answer: str):
    await answer_quiz_slash(interaction, "song2", answer)

# --- Answering seiyuu --- #
@bot.command(name="malecharacter", aliases=["mc"])
async def male_character_answer_quiz(
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
        ctx=ctx, quiz_type_id=1, quiz_type_name="Male Character", answer=answer
    )

@bot.command(name="femalecharacter", aliases=["fc"])
async def female_character_answer_quiz(ctx: commands.Context):
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
        ctx=ctx, quiz_type_id=2, quiz_type_name=" Female Character", answer=answer
    )

@bot.command(name="femalecharacter2", aliases=["fc2"])
async def female_character_2_answer_quiz(ctx: commands.Context):
    """
    Answer today's male image quiz.
    Please use ||spoiler tags|| to hide your answer.

    Arguments
    ---------
    answer : str
        The answer to the quiz.

    Examples
    ---------
    !maleimage ||your answer||
    !mi ||your answer||
    """

    answer = ctx.message.content.split(" ", 1)[1:]

    # edit their message to hide the answer
    await ctx.message.delete()

    # join the answer
    answer = " ".join(answer)

    await answer_quiz_type(
        ctx=ctx, quiz_type_id=3, quiz_type_name="Female Character 2", answer=answer
    )

@bot.command(name="song", aliases=["s"])
async def song_answer_quiz(ctx: commands.Context):
    """
    Answer today's female image quiz.
    Please use ||spoiler tags|| to hide your answer.

    Arguments
    ---------
    answer : str
        The answer to the quiz.

    Examples
    ---------
    !femaleimage ||your answer||
    !fi ||your answer||
    """

    answer = ctx.message.content.split(" ", 1)[1:]

    # edit their message to hide the answer
    await ctx.message.delete()

    # join the answer
    answer = " ".join(answer)

    await answer_quiz_type(
        ctx=ctx, quiz_type_id=4, quiz_type_name="Song", answer=answer
    )

@bot.command(name="song2", aliases=["s2"])
async def song_2_answer_quiz(ctx: commands.Context):
    """
    Answer today's song quiz.
    Please use ||spoiler tags|| to hide your answer.

    Arguments
    ---------
    answer : str
        The answer to the quiz.

    Examples
    ---------
    !song ||your answer||
    !s ||your answer||
    """

    answer = ctx.message.content.split(" ", 1)[1:]

    # edit their message to hide the answer
    await ctx.message.delete()

    # join the answer
    answer = " ".join(answer)

    await answer_quiz_type(
        ctx=ctx, quiz_type_id=5, quiz_type_name="Song 2", answer=answer
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
            value=f"Please provide an answer: `!{quiz_type_name.lower().replace(' ', '')} ||your answer||`",
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
                    value=f"You have already answered correctly for today's {quiz_type_name} quiz.\nBut you haven't answered the bonus character point yet. Use `!{quiz_type_name.lower().replace(' ', '')}bonus ||your answer||` to answer it.",
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

        # Check if correct
        quiz_answers = quiz_answer.split("|")
        is_correct = any(
            re.search(user_answer_pattern, a.strip(), re.IGNORECASE) for a in quiz_answers
        )

        # Always compute similarity (for incorrect answers too)
        similarities = [
            SequenceMatcher(None, answer.lower(), a.lower().strip()).ratio()
            for a in quiz_answers
        ]
        similarity_percentage = round(max(similarities) * 100, 2) if similarities else 0

        if is_correct:
            # ✅ Correct answer
            if not has_correct_bonus and quiz.bonus_answer:
                bonus_point_feedback = f" (you can also try to get the bonus point using `!{quiz_type_name.lower().replace(' ', '')}bonus ||your answer||`)"
            else:
                bonus_point_feedback = ""

            embed.add_field(
                name="Answer",
                value=f"✅ Correct in {answer_time}s!{bonus_point_feedback}",
                inline=True,
        )

            with bot.session as session:
                user_answer.is_correct = True
                session.add(user_answer)
                session.commit()

            await ctx.send(embed=embed)
            return

        else:
            # ❌ Wrong answer
            close_feedback = ""
            if similarity_percentage >= 75:
                close_feedback = f" ({similarity_percentage}%)"

            embed.add_field(
                name="Answer",
                value=f"❌ Incorrect in {answer_time}s {close_feedback}",
                inline=True,
            )

            with bot.session as session:
                user_answer.is_correct = False
                session.add(user_answer)
                session.commit()

            await ctx.send(embed=embed)
            return

# --- Answering character --- #
@bot.command(name="mcb", aliases=["malecharacterbonus"])
# Add other decorators as needed
async def male_character_bonus_answer_quiz(
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
    !malebonus ||your answer||
    !mb ||your answer||
    !malecharacter ||your answer||
    !ma ||your answer||
    """

    # edit their message to hide the answer
    await ctx.message.delete()

    # join the answer
    answer = " ".join(answer)

    await answer_bonus_quiz(
        ctx=ctx, quiz_type_id=1, quiz_type_name="Male Character", answer=answer
    )

@bot.command(
    name="fcb", aliases=["femalecharacterbonus"]
)
# Add other decorators as needed
async def female_character_bonus_answer_quiz(
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
    !femalebonus ||your answer||
    !fb ||your answer||
    !femalecharacter ||your answer||
    !fc ||your answer||
    """

    # edit their message to hide the answer
    await ctx.message.delete()

    # join the answer
    answer = " ".join(answer)

    await answer_bonus_quiz(
        ctx=ctx, quiz_type_id=2, quiz_type_name="Female Character", answer=answer
    )

@bot.command(name="fc2b", aliases=["fcb2","femalecharacter2bonus","femalecharacterbonus2"])
async def female_character_2_bonus_answer_quiz(ctx: commands.Context, *answer: str):
    """
    Answer today's male image quiz bonus.
    Please use ||spoiler tags|| to hide your answer.

    Arguments
    ---------
    answer : str
        The answer to the quiz.

    Examples
    ---------
    !maleimagebonus ||your answer||
    !mib ||your answer||
    """

    # Delete the user's message to hide the answer
    await ctx.message.delete()

    # Join the provided answer parts into a single string
    answer = " ".join(answer)

    await answer_bonus_quiz(
        ctx=ctx, quiz_type_id=3, quiz_type_name="Female Character 2", answer=answer
    )

@bot.command(name="songbonus", aliases=["sb"])
async def song_bonus_answer_quiz(ctx: commands.Context, *answer: str):
    """
    Answer today's female image quiz bonus.
    Please use ||spoiler tags|| to hide your answer.

    Arguments
    ---------
    answer : str
        The answer to the quiz.

    Examples
    ---------
    !femaleimagebonus ||your answer||
    !fib ||your answer||
    """

    # Delete the user's message to hide the answer
    await ctx.message.delete()

    # Join the provided answer parts into a single string
    answer = " ".join(answer)

    await answer_bonus_quiz(
        ctx=ctx, quiz_type_id=4, quiz_type_name="Song", answer=answer
    )

@bot.command(name="song2bonus", aliases=["s2b","sb2","songbonus2"])
async def song_2_bonus_answer_quiz(ctx: commands.Context, *answer: str):
    """
    Answer today's song quiz bonus.
    Please use ||spoiler tags|| to hide your answer.

    Arguments
    ---------
    answer : str
        The answer to the quiz.

    Examples
    ---------
    !songbonus ||your answer||
    !sb ||your answer||
    """

    # Delete the user's message to hide the answer
    await ctx.message.delete()

    # Join the provided answer parts into a single string
    answer = " ".join(answer)

    await answer_bonus_quiz(
        ctx=ctx, quiz_type_id=5, quiz_type_name="Song 2", answer=answer
    )

async def answer_bonus_quiz(
    ctx: commands.Context,
    quiz_type_id: int,
    quiz_type_name: str,
    answer: str,
):
    """
    Attempt to earn the bonus point for today's quiz, once the main quiz has been answered correctly.
    """

    answer_time = datetime.now()

    # Sanitize the answer
    answer = answer.replace('"', "")
    answer = re.sub(r"\|\|", "", answer).strip()

    embed = discord.Embed(
        title=f"{quiz_type_name} Quiz Bonus Results",
        color=0xBBE6F3,
    )

    embed.set_author(
        name=ctx.author.name,
        icon_url=ctx.author.avatar.url,
    )

    if not answer:
        embed.add_field(
            name="Invalid",
            value=f"Please provide an answer: `!{quiz_type_name.lower().replace(' ', '')}bonus ||your answer||`",
            inline=True,
        )
        await ctx.send(embed=embed)
        return

    with bot.session as session:
        current_quiz_date = get_current_quiz_date(
            daily_quiz_reset_time=DAILY_QUIZ_RESET_TIME
        )

        quiz = (
            session.query(Quiz)
            .filter(Quiz.id_type == quiz_type_id, Quiz.date == current_quiz_date)
            .first()
        )

        if not quiz:
            embed.add_field(
                name="Invalid",
                value=f"No {quiz_type_name} quiz available today. :disappointed_relieved:",
                inline=True,
            )
            await ctx.send(embed=embed)
            return

        if not quiz.bonus_answer:
            embed.add_field(
                name="Invalid",
                value=f"There is no bonus available for today's {quiz_type_name} quiz.",
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
                value=(
                    f"You haven't correctly answered today's {quiz_type_name} quiz yet.\n"
                    f"Use `!{quiz_type_name.lower().replace(' ', '')} ||your answer||` to submit your main answer first."
                ),
                inline=True,
            )
            await ctx.send(embed=embed)
            return

        if has_correct_bonus:
            embed.add_field(
                name="Already Completed",
                value=f"You have already claimed the bonus for today's {quiz_type_name} quiz.",
                inline=True,
            )
            await ctx.send(embed=embed)
            return

        # Retrieve the user's quiz start time for time calculation
        start_quiz_timestamp = (
            session.query(UserStartQuizTimestamp)
            .filter(
                UserStartQuizTimestamp.user_id == user.id,
                UserStartQuizTimestamp.quiz_id == quiz.id,
            )
            .first()
        )

        # Calculate answer time
        answer_duration = answer_time - start_quiz_timestamp.timestamp
        answer_duration_sec = round(answer_duration.total_seconds(), 3)

        # Prepare the new answer entry
        new_answer = Answer(
            user_id=user.id,
            quiz_id=quiz.id,
            answer="\\Bonus Answer\\",
            bonus_answer=answer,
            answer_time=answer_duration_sec,
            is_correct=False,
        )

        quiz_bonus_answer = quiz.bonus_answer.replace('"', "")

        user_bonus_answer_pattern = process_user_input(
            input_str=answer, partial_match=False, swap_words=True
        )

        quiz_bonus_answers = quiz_bonus_answer.split("|")

        # Check if correct
        is_correct_bonus = any(
            re.search(user_bonus_answer_pattern, a.strip(), re.IGNORECASE)
            for a in quiz_bonus_answers
        )

        # Always compute similarity (for incorrect answers too)
        similarities = [
            SequenceMatcher(None, answer.lower(), a.lower().strip()).ratio()
            for a in quiz_bonus_answers
        ]
        similarity_percentage = round(max(similarities) * 100, 2) if similarities else 0

        if is_correct_bonus:
            new_answer.is_bonus_point = True
            session.add(new_answer)
            session.commit()

            embed.add_field(
                name="Bonus Answer",
                value=f"✅ Correct! You claimed the bonus in {answer_duration_sec}s.",
                inline=True,
            )
        else:
            new_answer.is_bonus_point = False
            session.add(new_answer)
            session.commit()

            close_feedback = ""
            if similarity_percentage >= 75:
                close_feedback = f" ({similarity_percentage}%)"

            embed.add_field(
                name="Bonus Answer",
                value=f"❌ Incorrect in {answer_duration_sec}s {close_feedback}",
                inline=True,
            )
        await ctx.send(embed=embed)

@bot.command(name="mystats", aliases=["stats", "ms"])
# Add other decorators as needed
async def my_stats(ctx: commands.Context, user_id: Optional[int] = None):
    """
    Get your stats.

    Examples
    ---------
    !mystats
    !stats
    !ms
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

        pages = []
        quiz_types = session.query(QuizType).all()
        for quiz_type in quiz_types:

            # create the embed object
            embed = discord.Embed(title="")

            # set the author
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url)

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

            embed.add_field(name="", value="", inline=False)

            pages.append(embed)

    paginator = EmbedPaginatorSession(ctx, *pages)
    await paginator.run()

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
        fastest_answers_db = (
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
        for fastest_answer in fastest_answers_db:
            nb_attempts.append(
                session.query(Answer)
                .filter(
                    Answer.user_id == fastest_answer.user_id,
                    Answer.quiz_id == fastest_answer.quiz_id,
                    Answer.answer != "\\Bonus Answer\\",
                )
                .count()
            )

        fastest_answers = []
        for i, answer in enumerate(fastest_answers_db):
            rank = f"{medals[i]} " if i < 3 else f"#{i + 1} |"

            # Split and clean all aliases
            all_answers = [a.strip() for a in answer.quiz.answer.split("|") if a.strip()]
            main_character = all_answers[0] if len(all_answers) > 0 else "?"
            main_seiyuu = all_answers[1] if len(all_answers) > 1 else None

            # Normalize for matching
            user_guess = answer.answer.strip()
            matched_alias = None
            for alias in all_answers:
                pattern = process_user_input(alias, partial_match=False, swap_words=True)
                if re.fullmatch(pattern, user_guess, re.IGNORECASE):
                    matched_alias = alias
                    break

            # Formatting display
            if matched_alias:
                if matched_alias.lower() == main_character.lower():
                    display_text = f"**{main_character}**" if not main_seiyuu else f"**{main_character}** / {main_seiyuu}"
                elif main_seiyuu and matched_alias.lower() == main_seiyuu.lower():
                    display_text = f"{main_character} / **{main_seiyuu}**"
                elif main_seiyuu:
                    display_text = f"{main_character} / {main_seiyuu} (**{matched_alias}**)"
                else:
                    display_text = f"{main_character} (**{matched_alias}**)"
            else:
                display_text = f"{main_character}" if not main_seiyuu else f"{main_character} / {main_seiyuu}"

            value = f"{rank} **{answer.answer_time:.3f}s** - {display_text}\n> in {nb_attempts[i]} attempt(s) / {answer.quiz.date}"
            fastest_answers.append(value)

        fastest_answers_str = "\n\n".join(fastest_answers)
        embed.add_field(name="__Fastest Guesses__", value=fastest_answers_str, inline=True)
        
    return embed


@bot.command(name="fcg", aliases=["femalecharacterguesses"])
async def my_female_guesses(ctx: Context, user_id: Optional[int] = None):
    """
    Get your female character stats.

    Examples
    ---------
    !femalecharacterguesses
    !fcg
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

        quiz_type = session.query(QuizType).get(2)  # female quiz type
        mgpages = []

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

        if not mgpages:
            await ctx.send(
                f"{ctx.author.mention} You don't have any female character guesses yet."
            )
            return

        paginator = EmbedPaginatorSession(ctx, *mgpages)
        await paginator.run()


@bot.command(name="mcg", aliases=["malecharacterguesses"])
async def my_male_guesses(ctx: Context, user_id: Optional[int] = None):
    """
    Get your male character stats.

    Examples
    ---------
    !malecharacterguesses
    !mcg
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

        quiz_type = session.query(QuizType).get(1)  # male quiz type
        mgpages = []

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

        if not mgpages:
            await ctx.send(f"{ctx.author.mention} You don't have any male character guesses yet.")
            return

        paginator = EmbedPaginatorSession(ctx, *mgpages)
        await paginator.run()

@bot.command(name="fc2g", aliases=["femalecharacter2guesses"])
async def my_image_guesses(ctx: Context, user_id: Optional[int] = None):
    """
    Get your female character 2 stats.

    Examples
    ---------
    !femalecharacterguesses2
    !fcg2
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

        quiz_type = session.query(QuizType).get(3)
        mgpages = []

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

        if not mgpages:
            await ctx.send(
                f"{ctx.author.mention} You don't have any female character 2 guesses yet."
            )
            return

        paginator = EmbedPaginatorSession(ctx, *mgpages)
        await paginator.run()


@bot.command(name="sg", aliases=["songguesses"])
async def my_image_guesses(ctx: Context, user_id: Optional[int] = None):
    """
    Get your female image stats.

    Examples
    ---------
    !songguesses
    !sg
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

        quiz_type = session.query(QuizType).get(4)
        mgpages = []

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

        if not mgpages:
            await ctx.send(
                f"{ctx.author.mention} You don't have any song guesses yet."
            )
            return

        paginator = EmbedPaginatorSession(ctx, *mgpages)
        await paginator.run()

@bot.command(name="song2guesses", aliases=["s2g"])
async def my_song_guesses(ctx: Context, user_id: Optional[int] = None):
    """
    Get your song stats.

    Examples
    ---------
    !song2guesses
    !s2g
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

        quiz_type = session.query(QuizType).get(5)
        mgpages = []

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

        if not mgpages:
            await ctx.send(f"{ctx.author.mention} You don't have any song 2 guesses yet.")
            return

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
            embed = discord.Embed(
                title=f"Top Guesses for {quiz_type.type}",
                color=0xBBE6F3,
            )
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url)

            page_end = np.min([page_start + 10, len(fastest_answers)])

            for i, answer in enumerate(
                fastest_answers[page_start:page_end], start=page_start
            ):
                rank = f"{medals[i % 3]} " if i < 3 else f"#{i + 1} |"

                # Split and clean all aliases (remove empty strings and extra spaces)
                all_answers = [a.strip() for a in answer.quiz.answer.split("|") if a.strip()]

                # Determine main names (first two if available)
                main_character = all_answers[0] if len(all_answers) > 0 else "?"
                main_seiyuu = all_answers[1] if len(all_answers) > 1 else None  # Could be None if only one alias

                # Normalize everything for comparison
                user_guess = answer.answer.strip()
                all_lower = [a.lower() for a in all_answers]

                # Find matched alias
                matched_alias = None
                for alias in all_answers:
                    # Use the same normalization as in the quiz answer phase
                    pattern = process_user_input(alias, partial_match=False, swap_words=True)
                    if re.fullmatch(pattern, user_guess, re.IGNORECASE):
                        matched_alias = alias
                        break

                # Formatting display
                if matched_alias:
                    if matched_alias.lower() == main_character.lower():
                        display_text = f"**{main_character}**" if not main_seiyuu else f"**{main_character}** / {main_seiyuu}"
                    elif main_seiyuu and matched_alias.lower() == main_seiyuu.lower():
                        display_text = f"{main_character} / **{main_seiyuu}**"
                    elif main_seiyuu:
                        # Matched a later alias → show in parentheses
                        display_text = f"{main_character} / {main_seiyuu} (**{matched_alias}**)"
                    else:
                        # Only one main alias
                        display_text = f"{main_character} (**{matched_alias}**)"
                else:
                    # Fallback if no match
                    display_text = f"{main_character}" if not main_seiyuu else f"{main_character} / {main_seiyuu}"

                # Split info lines for readability
                value = (
                    f"{rank} **{answer.answer_time:.3f}s** - {display_text}\n"
                    f"> in {nb_attempts[i]} attempt(s) / {answer.quiz.date}"
                )

                embed.add_field(name="", value=value, inline=False)

            mgpages.append(embed)

@bot.tree.command(name="ct")
async def current_top(interaction: discord.Interaction):
    """Show today's fastest correct answers for quizzes you've opened or created, with user attempt counts."""
    with bot.session as session:
        current_quiz_date = get_current_quiz_date(DAILY_QUIZ_RESET_TIME)
        tomorrow_reset_date = current_quiz_date + timedelta(days=1)

        # --- Get opened quizzes
        opened_quiz_ids = [
            qid for (qid,) in session.query(UserStartQuizTimestamp.quiz_id)
            .filter(UserStartQuizTimestamp.user_id == interaction.user.id)
            .all()
        ]

        # --- Get created quizzes
        created_quiz_ids = [
            qid for (qid,) in session.query(Quiz.id)
            .filter(
                Quiz.creator_id == interaction.user.id,
                Quiz.date >= current_quiz_date,
                Quiz.date < tomorrow_reset_date,
            )
            .all()
        ]

        # --- Combine both
        all_relevant_quiz_ids = list(set(opened_quiz_ids + created_quiz_ids))

        if not all_relevant_quiz_ids:
            await interaction.response.send_message(
                "You haven't opened or created any quizzes today.",
                ephemeral=True,
            )
            return

        # --- Get fastest correct answers
        fastest_answers = (
            session.query(Answer, QuizType, Quiz)
            .join(Quiz, Answer.quiz_id == Quiz.id)
            .join(QuizType, Quiz.id_type == QuizType.id)
            .filter(
                Answer.is_correct,
                Quiz.date >= current_quiz_date,
                Quiz.date < tomorrow_reset_date,
                Quiz.id.in_(all_relevant_quiz_ids),
                Answer.answer != "\\Bonus Answer\\",
            )
            .order_by(QuizType.id, Answer.answer_time)
            .all()
        )

        quiz_types = session.query(QuizType).all()
        medals = [":first_place:", ":second_place:", ":third_place:"]

        # --- Group by quiz type
        results_by_type = {qt.type: [] for qt in quiz_types}
        for answer, quiz_type, quiz in fastest_answers:
            results_by_type[quiz_type.type].append(
                (answer.user.id, answer.answer_time, quiz_type.emoji)
            )

        # --- Helper for chunking into pairs
        def chunked(iterable, size):
            it = iter(iterable)
            return iter(lambda: tuple(islice(it, size)), ())

        # --- Convert quiz_types into a list so we can chunk them
        quiz_type_items = list(quiz_types)

        embeds = []

        # --- Loop through quiz types in groups of 3 (side by side)
        for quiz_chunk in chunked(quiz_type_items, 3):
            embed = discord.Embed(
                title="Today's Top Guesses",
                description="Fastest correct answers from today",
                color=0xBBE6F3,
            )
            embed.set_author(
                name=interaction.user.name,
                icon_url=interaction.user.avatar.url,
            )

            for quiz_type in quiz_chunk:
                user_times = results_by_type[quiz_type.type]
                value = ""

                # --- 🆕 Get total attempts for this quiz type
                total_attempts_type = (
                    session.query(Answer)
                    .join(Quiz, Answer.quiz_id == Quiz.id)
                    .filter(
                        Quiz.date >= current_quiz_date,
                        Quiz.date < tomorrow_reset_date,
                        Quiz.id_type == quiz_type.id,
                        Quiz.id.in_(all_relevant_quiz_ids),
                        Answer.answer != "\\Bonus Answer\\",
                    )
                    .count()
                )

                if user_times:
                    user_times.sort(key=lambda x: x[1])
                    for j, (user_id, time, emoji) in enumerate(user_times[:10]):
                        rank = f"{medals[j]} " if j < 3 else f"#{j + 1}: "

                        # Count only non-bonus attempts by that user
                        total_attempts_user = (
                            session.query(Answer)
                            .join(Quiz, Answer.quiz_id == Quiz.id)
                            .filter(
                                Quiz.date >= current_quiz_date,
                                Quiz.date < tomorrow_reset_date,
                                Quiz.id_type == quiz_type.id,
                                Quiz.id.in_(all_relevant_quiz_ids),
                                Answer.user_id == user_id,
                                Answer.answer != "\\Bonus Answer\\",
                            )
                            .count()
                        )

                        value += (
                            f"> {rank} <@{user_id}> - **{time:.2f}s** "
                            f"({total_attempts_user} attempts)\n"
                        )
                else:
                    value = "> Unopened / No Hitters ⚠️"

                # --- 🆕 Include total attempts in field name
                embed.add_field(
                    name=f"> {quiz_type.emoji} {quiz_type.type} | Total Attempts: {total_attempts_type}",
                    value=value,
                    inline=True,
                )

            embed.add_field(name="", value="", inline=False)
            embeds.append(embed)

        paginator = EmbedPaginatorSession(interaction, *embeds, timeout=120)
        await paginator.run(ephemeral=True)

@bot.command(name="nobonusleaderboard", aliases=["nblb"])
# Add other decorators as needed
async def seiyuuleaderboard(ctx: commands.Context):
    """
    Basically the same leardboard as the main one, except it doesn't take into account the bonus character points.

    Examples
    ---------
    !nobonusleaderboard
    !nblb
    """

    if bot.last_leaderboard_update is not None and (
        datetime.now() - bot.last_leaderboard_update < timedelta(minutes=120)
    ):
        # write a message to let the user know that the leaderboard was already shown recently
        await ctx.send(
            f"Leaderboard without bonus was already shown recently. Please wait a bit before using this command again. You can search for the last leaderboard message in the channel with keywords '{config['COMMAND_PREFIX']}slb' or '{config['COMMAND_PREFIX']}seiyuuleaderboard'"
        )
        return

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

    bot.last_leaderboard_update = datetime.now()

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

    if bot.last_leaderboard_update is not None and (
        datetime.now() - bot.last_leaderboard_update < timedelta(minutes=120)
    ):
        # write a message to let the user know that the leaderboard was already shown recently
        await ctx.send(
            f"Leaderboard was already shown recently. Please wait a bit before using this command again. You can search for the last leaderboard message in the channel with keywords '{config['COMMAND_PREFIX']}lb' or '{config['COMMAND_PREFIX']}leaderboard'"
        )
        return

    with bot.session as session:
        users = session.query(User).all()
        quiz_types = session.query(QuizType).all()
        medals = [":first_place:", ":second_place:", ":third_place:"]

        # initialize the score dict
        user_scores = {"total": {user.id: 0 for user in users}}
        for quiz_type in quiz_types:
            user_scores[quiz_type.type] = {user.id: 0 for user in users}

        for i, user in enumerate(users):

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

        for idx_q, quiz_type in enumerate(quiz_types):
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

            # Linebreak every two types unless last type
            if (idx_q + 1) % 2 == 0 and idx_q != 0 and idx_q + 1 != len(quiz_types):
                embed.add_field(name="\u200b", value="", inline=False)

        value = ""
        embed.add_field(name="\u200b", value="", inline=False)
        for i, id_user in enumerate(
            list(user_scores["total"].keys())[page_start:page_end]
        ):
            index = page_start + i
            rank = f"{medals[index]} " if index < 3 else f"#{index + 1}: "
            value += f"> {rank} <@{id_user}> - {user_scores['total'][id_user]} points\n"
        embed.add_field(name="> Global Leaderboard", value=value, inline=False)

        pages.append(embed)

    bot.last_leaderboard_update = datetime.now()

    session = EmbedPaginatorSession(ctx, *pages)
    await session.run()

async def compute_user_score(id_user: int, id_quiz_type: int, bonus_points=True):
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

        # Combined query to get attempts for both regular and bonus points
        attempts = (
            session.query(
                Answer.quiz_id,
                func.count(Answer.id).label("nb_attempts"),
                case((Answer.is_bonus_point, "bonus"), else_="regular").label("type"),
            )
            .join(Quiz)
            .filter(
                Answer.user_id == id_user,
                Quiz.id_type == id_quiz_type,
                Answer.is_correct | Answer.is_bonus_point,
            )
            .group_by(
                Answer.quiz_id, case((Answer.is_bonus_point, "bonus"), else_="regular")
            )
            .all()
        )

        nb_points = 0

        for attempt in attempts:
            nb_attempts = attempt.nb_attempts
            if attempt.type == "regular":
                nb_point = 1 if nb_attempts <= 5 else 0.5 if nb_attempts <= 8 else 0.25
                nb_points += nb_point
            elif attempt.type == "bonus" and bonus_points:
                nb_point = 0.5 if nb_attempts <= 3 else 0.25
                nb_points += nb_point

        return round(float(nb_points), 2)

@bot.tree.command(name="log")
async def history(interaction: discord.Interaction):
    """Get your answer history for today's quiz."""

    with bot.session as session:
        user = get_user(session=session, user=interaction.user, add_if_not_exist=True)
        current_quiz_date = get_current_quiz_date(DAILY_QUIZ_RESET_TIME)
        quiz_types = session.query(QuizType).all()

        # Helper for chunking a list
        def chunked(iterable, size):
            it = iter(iterable)
            return iter(lambda: tuple(islice(it, size)), ())

        pages = []
        lines_per_page = 20  # ~20 lines max per embed

        all_lines = []
        header = f"Today's History for {interaction.user.name}\n\n"

        # Collect all lines of text before paginating
        for quiz_type in quiz_types:
            all_lines.append(f"__**{quiz_type.emoji} {quiz_type.type}**__")

            # Get all answers for this quiz type
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

            if not answers:
                all_lines.append(f"> You haven't answered today's {quiz_type.type} quiz yet.\n")
                continue

            for answer in answers:
                if answer.answer != "\\Bonus Answer\\":
                    mark = "✅" if answer.is_correct else "❌"
                    all_lines.append(f"> {mark} {answer.answer} in {answer.answer_time}s")
                else:
                    mark = "✅" if answer.is_bonus_point else "❌"
                    all_lines.append(f"> {mark} {answer.bonus_answer} in {answer.answer_time}s")

            all_lines.append("")  # blank line between types

        # Split all_lines into pages of ~20 lines
        for chunk in chunked(all_lines, lines_per_page):
            page_text = "\n".join(chunk)
            embed = discord.Embed(
                title="Today's History",
                description=page_text,
                color=0xBBE6F3,
            )
            embed.set_author(
                name=interaction.user.name,
                icon_url=interaction.user.avatar.url,
            )
            pages.append(embed)

    # Handle empty case
    if not pages:
        await interaction.response.send_message(
            "You haven’t answered any quizzes today.",
            ephemeral=True,
        )
        return

    # If only one page, send it directly
    if len(pages) == 1:
        await interaction.response.send_message(embed=pages[0], ephemeral=True)
        return

    # If multiple pages, use the paginator (same style as /ct)
    session = EmbedPaginatorSession(interaction, *pages, disable_stop=True)

    await session.run(ephemeral=True)

@bot.event
async def post_yesterdays_quiz_results():
    # Calculate the date for yesterday
    current_quiz_date = get_current_quiz_date(DAILY_QUIZ_RESET_TIME)
    yesterday = current_quiz_date - timedelta(days=1)

    # Query the database for the quiz that matches the calculated date
    with bot.session as session:
        quiz_types = session.query(QuizType).all()
        for i, quiz_type in enumerate(quiz_types):
            # get yesterday's quiz
            yesterday_quiz = (
                session.query(Quiz)
                .filter(Quiz.id_type == quiz_type.id, Quiz.date == yesterday)
                .first()
            )

            embed = discord.Embed(
                title=f"Yesterday's {quiz_type.type} Quiz Results",
                color=0xBBE6F3,
            )

            if not yesterday_quiz:
                embed.add_field(
                    name=f"There was no {quiz_type.type} quiz yesterday.",
                    value="",
                    inline=False,
                )
                # send it on every channels set as quiz channel
                for quiz_channel in session.query(QuizChannels).all():
                    channel = bot.get_channel(quiz_channel.id_channel)
                    await channel.send(embed=embed)
                continue

            embed.set_footer(
                text=f"Quiz ID: {yesterday_quiz.id}",
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


@bot.tree.command(name="results", description="View the results for a specific quiz (only available if you played that quiz).")
@app_commands.describe(quiz_id="The quiz ID you want to see results for.")
async def results(interaction: discord.Interaction, quiz_id: int):
    await interaction.response.defer(ephemeral=True)

    with SessionFactory() as s:
        quiz = s.query(Quiz).get(quiz_id)
        if not quiz:
            await interaction.followup.send("❌ No quiz found with that ID.", ephemeral=True)
            return

        # ⛔ PREVENT FUTURE QUIZ LEAKING
        current_quiz_date = get_current_quiz_date(DAILY_QUIZ_RESET_TIME)
        if quiz.date > current_quiz_date:
            await interaction.followup.send(
                "❌ This quiz has not been released yet.",
                ephemeral=True,
            )
            return

        # Check if the user played that quiz
        played = (
            s.query(UserStartQuizTimestamp)
            .filter(
                UserStartQuizTimestamp.quiz_id == quiz_id,
                UserStartQuizTimestamp.user_id == interaction.user.id,
            )
            .first()
        )

        answered = (
            s.query(Answer)
            .filter(
                Answer.quiz_id == quiz_id,
                Answer.user_id == interaction.user.id,
            )
            .first()
        )

        if not answered:
            await interaction.followup.send(
                "❌ You must submit an answer for this quiz before you can view its results.",
                ephemeral=True,
            )
            return

        # Build compact results
        embed = await build_compact_results_embed(s, quiz)

    await interaction.followup.send(embed=embed, ephemeral=True)


async def build_compact_results_embed(session, quiz: Quiz):
    quiz_type = quiz.type  # relationship: Quiz.type → QuizType

    embed = discord.Embed(
        title=f"{quiz_type.emoji} Results for {quiz_type.type} Quiz",
        color=0xBBE6F3,
    )

    # Add answers
    answers = [a.strip() for a in quiz.answer.split("|")]
    answer_text = " / ".join(answers)
    embed.add_field(name="**Answer**", value=f"||{answer_text}||", inline=False)

    # Bonus answers
    if quiz.bonus_answer:
        bonus = [b.strip() for b in quiz.bonus_answer.split("|")]
        bonus_text = " / ".join(bonus)
        embed.add_field(name="**Bonus**", value=f"||{bonus_text}||", inline=False)

    # Count attempts
    attempts = (
        session.query(Answer)
        .filter(
            Answer.quiz_id == quiz.id,
            Answer.answer != "\\Bonus Answer\\",
        )
        .count()
    )

    correct = (
        session.query(Answer)
        .filter(
            Answer.quiz_id == quiz.id,
            Answer.is_correct,
        )
        .count()
    )

    embed.add_field(name="Attempts", value=str(attempts), inline=True)
    embed.add_field(name="Correct", value=str(correct), inline=True)

    # Add fastest 3
    fastest = (
        session.query(Answer)
        .filter(
            Answer.quiz_id == quiz.id,
            Answer.is_correct,
        )
        .order_by(Answer.answer_time)
        .limit(3)
        .all()
    )

    if fastest:
        top_guessers = "\n".join(
            f"> <@{a.user_id}> — {a.answer_time}s"
            for a in fastest
        )
        embed.add_field(name="Top Guessers", value=top_guessers, inline=False)

    embed.set_footer(text=f"Quiz ID: {quiz.id}")

    return embed


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

            if self.quiz_type.type in [
                "Male Character",
                "Female Character",
                "Female Character 2",
            ] and current_quiz.clip.endswith((".png", ".jpg", ".jpeg", ".gif", ".avif", ".webp")):
                embed.add_field(
                    name="",
                    value=current_quiz.clip,
                    inline=True,
                )
                embed.set_image(url=current_quiz.clip)
            else:
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

            quiz_types = session.query(QuizType).all()

            # change the order so that any "quiz_type.type" that contains "Image" is pushed to the end of the list
            quiz_types = sorted(
                quiz_types,
                key=lambda x: x.type.lower().endswith("image"),
            )

            for quiz_type in quiz_types:
                button = NewQuizButton(quiz_type=quiz_type, new_quiz_date=new_quiz_date)
                self.add_item(button)


# ----------------------------------
# -------  CATCHUP SECTION  --------
# ----------------------------------

CATCHUP_TYPE_CHOICES = {
    "Male Character": 1,
    "Female Character": 2,
    "Female Character 2": 3,
    "Song": 4,
    "Song 2": 5,
}

# ----------------------------
# Helper: missed quizzes (no today/tomorrow)
# ----------------------------

def get_missed_quizzes(session, user_id: int, id_type: Optional[int] = None):
    """
    Return list of Quiz objects the user has not started yet and that are older than yesterday.
    If id_type is provided, filter by that quiz type id.
    """
    today = date.today()
    cutoff = today - timedelta(days=1)  # strictly less than cutoff → older than yesterday

    started_ids = [u.quiz_id for u in session.query(UserStartQuizTimestamp).filter_by(user_id=user_id)]
    q = session.query(Quiz).filter(Quiz.date < cutoff)
    if id_type:
        q = q.filter(Quiz.id_type == id_type)
    if started_ids:
        q = q.filter(~Quiz.id.in_(started_ids))
    return q.all()

# ----------------------------
# Button views used in DMs
# ----------------------------

class CatchupControlView(View):
    def __init__(self, user_id: int, id_type: int):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.id_type = id_type
        self.add_item(ReadyButton(user_id, id_type))

class CatchupResultView(View):
    def __init__(self, user_id: int, id_type: int):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.id_type = id_type
        self.add_item(NextButton(user_id, id_type))
        self.add_item(SkipButton(user_id, id_type))
        self.add_item(StopButton(user_id))

class ReadyButton(Button):
    def __init__(self, user_id: int, id_type: int):
        super().__init__(label="I'm Ready", style=discord.ButtonStyle.success)
        self.user_id = user_id
        self.id_type = id_type

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your session!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await send_next_quiz(interaction.user, self.user_id, id_type=self.id_type)

class NextButton(Button):
    def __init__(self, user_id: int, id_type: int):
        super().__init__(label="Next Quiz", style=discord.ButtonStyle.primary)
        self.user_id = user_id
        self.id_type = id_type

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your session!", ephemeral=True)
            return

        with SessionFactory() as s:
            last_start = (
                s.query(UserStartQuizTimestamp)
                .filter_by(user_id=self.user_id)
                .order_by(UserStartQuizTimestamp.timestamp.desc())
                .first()
            )
            if not last_start:
                await interaction.response.send_message("No active quiz. Click Ready to begin.", ephemeral=True)
                return

            correct_exists = (
                s.query(Answer)
                .filter(
                    Answer.user_id == self.user_id,
                    Answer.quiz_id == last_start.quiz_id,
                    Answer.is_correct == True
                )
                .first()
            )

            if not correct_exists:
                await interaction.response.send_message(
                    "You must answer the current quiz correctly before moving to the next one, or click Skip to skip it.",
                    ephemeral=True
                )
                return

        await interaction.response.defer(ephemeral=True)
        await send_next_quiz(interaction.user, self.user_id, id_type=self.id_type)

class SkipButton(Button):
    def __init__(self, user_id: int, id_type: int):
        super().__init__(label="Skip", style=discord.ButtonStyle.secondary)
        self.user_id = user_id
        self.id_type = id_type

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your session!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await send_next_quiz(interaction.user, self.user_id, id_type=self.id_type)

class StopButton(Button):
    def __init__(self, user_id: int):
        super().__init__(label="Stop", style=discord.ButtonStyle.danger)
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your session!", ephemeral=True)
            return
        await interaction.response.send_message("Catch-up session ended. Use /catchup to resume later.", ephemeral=True)


# ----------------------------
# send_next_quiz: pick a missed quiz, store start timestamp, DM the user
# ----------------------------
async def send_next_quiz(user_obj_or_interaction, user_id: int, id_type: Optional[int] = None):
    # get a missed quiz while session is open to avoid DetachedInstanceError
    with SessionFactory() as s:
        missed = get_missed_quizzes(s, user_id, id_type=id_type)
        if not missed:
            # No missed quizzes left
            if isinstance(user_obj_or_interaction, discord.Interaction):
                # interaction provided → reply ephemeral
                await user_obj_or_interaction.followup.send("You've caught up on all missed quizzes for this selection!", ephemeral=True)
            else:
                await user_obj_or_interaction.send("You've caught up on all missed quizzes for this selection!")
            return

        next_quiz = random.choice(missed)

        # store a start timestamp now (prevents same quiz from being chosen again)
        start_ts = datetime.now()
        s.add(UserStartQuizTimestamp(user_id=user_id, quiz_id=next_quiz.id, timestamp=start_ts))
        s.commit()

        # copy fields we need while session is open
        quiz_id = next_quiz.id
        quiz_clip = next_quiz.clip
        # safe attempt to get the display string for the type
        try:
            quiz_type_string = next_quiz.type.type
        except Exception:
            quiz_type_string = f"type_id:{next_quiz.id_type}"

    # determine user object to DM
    if isinstance(user_obj_or_interaction, discord.Interaction):
        user_to_dm = user_obj_or_interaction.user
    else:
        user_to_dm = user_obj_or_interaction

    # build DM text and send
    dm_text = (
        f"**Quiz ID:** {quiz_id} | **Type:** {quiz_type_string}\n"
        f"{quiz_clip}\n\n"
    )

    try:
        await user_to_dm.send(dm_text, view=CatchupResultView(user_id))
    except discord.Forbidden:
        # can't DM user — if an interaction was given, inform ephemeral
        if isinstance(user_obj_or_interaction, discord.Interaction):
            await user_obj_or_interaction.followup.send("I couldn't DM you — please enable DMs from server members.", ephemeral=True)
        # otherwise nothing to do
        return

    # If called from an interaction, acknowledge the button (we already deferred earlier) and let them know
    if isinstance(user_obj_or_interaction, discord.Interaction):
        await user_obj_or_interaction.followup.send("Sent the quiz to your DMs.", ephemeral=True)




# ----------------------------
# /catchup slash command (choice for quiz type)
# ----------------------------
CATCHUP_CHOICES = [
    app_commands.Choice(name=label, value=label) for label in CATCHUP_TYPE_CHOICES.keys()
]

@bot.tree.command(name="catchup", description="Catch up on missed quizzes (choose a quiz type)")
@app_commands.describe(quiz_type="Which quiz type do you want to catch up on?")
@app_commands.choices(quiz_type=CATCHUP_CHOICES)
async def catchup(interaction: discord.Interaction, quiz_type: app_commands.Choice[str]):
    await interaction.response.defer(ephemeral=True)

    chosen_label = quiz_type.value
    chosen_id_type = CATCHUP_TYPE_CHOICES.get(chosen_label)
    if not chosen_id_type:
        await interaction.followup.send("Invalid quiz type selection.", ephemeral=True)
        return

    with SessionFactory() as s:
        missed = get_missed_quizzes(s, interaction.user.id, id_type=chosen_id_type)

    if not missed:
        await interaction.followup.send(f"No missed quizzes of type **{chosen_label}**.", ephemeral=True)
        return

    try:
        intro_text = (
            f"Welcome to Catch-up for **{chosen_label}**.\n\n" 
            f"You'll receive missed quizzes (quizzes that you've **never** opened, not the ones that you didn't hit.)\n"
            f"Make **sure** that the `/answer <>` command is loaded. If not, reload your discord client and check again.\n" 
            f"The **quiz** and **timer** starts once you click the **I'm Ready**/**Next Quiz** button.\n"
        )
        await interaction.user.send(intro_text, view=CatchupControlView(interaction.user.id, chosen_id_type))
    except discord.Forbidden:
        await interaction.followup.send("I couldn't DM you — please enable DMs from server members.", ephemeral=True)
        return

    await interaction.followup.send(f"Check your DMs to start catching up on {chosen_label}(s)!", ephemeral=True)


# ----------------------------
# /answer slash command for catchup flow
# ----------------------------
@bot.tree.command(name="answer", description="Answer the current catch-up quiz")
@app_commands.describe(answer="Your answer for the current quiz")
async def answer(interaction: discord.Interaction, answer: str):
    user_id = interaction.user.id
    answer = re.sub(r"\|\|", "", answer).strip()

    # find the user's last started quiz (the one they should be answering)
    with SessionFactory() as s:
        last_start = (
            s.query(UserStartQuizTimestamp)
            .filter_by(user_id=user_id)
            .order_by(UserStartQuizTimestamp.timestamp.desc())
            .first()
        )
        if not last_start:
            await interaction.response.send_message("You have no active catch-up quiz. Use /catchup to start.", ephemeral=True)
            return

        # load quiz and copy needed fields while the session is open
        quiz = s.query(Quiz).filter_by(id=last_start.quiz_id).first()
        if not quiz:
            await interaction.response.send_message("Quiz not found.", ephemeral=True)
            return

        quiz_id = quiz.id
        quiz_answer_raw = quiz.answer or ""
        quiz_clip = quiz.clip or ""
        quiz_type_string = None
        try:
            quiz_type_string = quiz.type.type
        except Exception:
            quiz_type_string = f"type_id:{quiz.id_type}"

        # Get all prior attempts for duplicate prevention
        prior_attempts = (
            s.query(Answer)
            .filter(
                Answer.user_id == user_id,
                Answer.quiz_id == quiz_id
            )
            .all()
        )

        # Helper duplicate detector using your process_user_input rules
        def is_duplicate(previous_text: str, current_text: str) -> bool:
            if not previous_text or not current_text:
                return False
            pattern = process_user_input(previous_text, partial_match=False, swap_words=True)
            return re.fullmatch(pattern, current_text, re.IGNORECASE) is not None

        duplicate_of_before = any(
            is_duplicate(
                (pr.answer if pr.answer != "\\Bonus Answer\\" else (pr.bonus_answer or "")),
                answer
            )
            for pr in prior_attempts
        )

        if duplicate_of_before:
            embed = discord.Embed(
                title=f"{quiz_type_string} Results",
                color=0xBBE6F3
            )
            embed.set_author(name=interaction.user.name, icon_url=interaction.user.avatar.url)
            embed.add_field(name="Duplicate", value="⚠️ You've already tried that exact answer. (Does not get recorded.)", inline=True)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Prepare correctness check using your process_user_input rules
        user_pattern = process_user_input(answer, partial_match=False, swap_words=True)
        main_aliases = [a.strip() for a in quiz_answer_raw.split("|") if a.strip()]

        is_main_correct = any(re.search(user_pattern, a, re.IGNORECASE) for a in main_aliases)

        # similarity for feedback
        similarities = [SequenceMatcher(None, answer.lower(), a.lower().strip()).ratio() for a in (main_aliases or [""])]
        similarity_pct = round(max(similarities) * 100, 2) if similarities else 0

        # Calculate answer duration using the recorded start timestamp
        duration = (datetime.now() - last_start.timestamp).total_seconds()
        duration = round(duration, 3)

        # Record the attempt (main)
        entry = Answer(
            user_id=user_id,
            quiz_id=quiz_id,
            answer=answer,
            answer_time=duration,
            is_correct=is_main_correct,
            bonus_answer=None,
            is_bonus_point=False
        )
        s.add(entry)
        s.commit()

        # Build response embed
        embed = discord.Embed(
            title=f"{quiz_type_string} Quiz Results",
            color=0xBBE6F3
        )
        embed.set_author(name=interaction.user.name, icon_url=interaction.user.avatar.url)

        if is_main_correct:
            embed.add_field(name="Answer", value=f"✅ Correct in {duration}s!", inline=True)
            # next/skip/stop provided in the DM by the earlier view; respond ephemeral to slash
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        else:
            close_feedback = f" ({similarity_pct}%)" if similarity_pct >= 75 else ""
            embed.add_field(name="Answer", value=f"❌ Incorrect in {duration}s{close_feedback}\nTry again or click Skip to move on.", inline=True)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return




# ----------------------------------
# ----- SERVER ADMIN COMMANDS ------
# ----------------------------------

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

@bot.tree.command(name="nq")
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

@bot.tree.command(name="sss")
@app_commands.choices(quiz_type=get_quiz_type_choices(session=bot.session))
@app_commands.describe(
    quiz_type="type of the quiz to submit",
    clip=".png / .mp3 link",
    answer="correct answer ",
    bonus_answer="The bonus answer for the submission",
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
    await interaction.response.send_message("✅", ephemeral=True)
    # Send the result as a direct message to the user
    await interaction.user.send(
        f"Submission for {quiz_type.name} added for {new_date}\n ||[{answer}]({clip})|| {'+ ||' + bonus_answer if bonus_answer else ''}||"
    )

@bot.tree.command(name="pq")
async def planned_quizzes(interaction: discord.Interaction):
    """**Bot Admin Only** - Check the planned quizzes you've already opened."""

    with bot.session as session:
        # check if user is a bot admin
        if not is_bot_admin(session=session, user=interaction.user):
            await interaction.response.send_message(
                "You are not an admin, you can't use this command."
            )
            return

        current_quiz_date = get_current_quiz_date(
            daily_quiz_reset_time=DAILY_QUIZ_RESET_TIME
        )

        # get all quiz IDs that this user (admin) has opened
        opened_quiz_ids = (
            session.query(UserStartQuizTimestamp.quiz_id)
            .filter(UserStartQuizTimestamp.user_id == interaction.user.id)
            .subquery()
        )

        # get all unique quiz dates that are after or equal to current date
        # and are in the opened_quiz_ids list
        unique_date = (
            session.query(Quiz.date)
            .filter(
                Quiz.date >= current_quiz_date,
                Quiz.id.in_(opened_quiz_ids),
            )
            .distinct()
            .all()
        )

        if not unique_date:
            await interaction.response.send_message(
                f"You haven’t opened any planned quizzes after {current_quiz_date}."
            )
            return

        embed = discord.Embed(
            title="Planned Quizzes You’ve Opened",
            color=discord.Color.blurple()
        )

        quiz_types = session.query(QuizType).all()

        for i, quiz_date in enumerate(unique_date):
            quiz_date = quiz_date[0]

            embed.add_field(
                name=f":calendar_spiral: __**{quiz_date if i != 0 else 'Today'}**__",
                value="",
                inline=False,
            )

            for j, quiz_type in enumerate(quiz_types):
                quiz = (
                    session.query(Quiz)
                    .filter(
                        Quiz.id_type == quiz_type.id,
                        Quiz.date == quiz_date,
                        Quiz.id.in_(opened_quiz_ids),
                    )
                    .first()
                )

                if quiz:
                    value = f"||[{quiz.answer}]({quiz.clip})||"
                    if quiz.bonus_answer:
                        value += f" + ||{quiz.bonus_answer}||"
                    value += f" by <@{quiz.creator_id}>"
                else:
                    value = "Unplanned/Unopened"

                embed.add_field(
                    name=f"> {quiz_type.emoji} {quiz_type.type}",
                    value=f"> {value}",
                    inline=True,
                )

                # line break after every two inline fields
                if (j + 1) % 2 == 0 and j != 0 and j + 1 != len(quiz_types):
                    embed.add_field(name="", value="", inline=False)

            # add spacer between dates
            if quiz_date != unique_date[-1][0]:
                embed.add_field(name="\u200b", value="", inline=False)

        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="qq")
async def queue(interaction: discord.Interaction):
    """Check the planned quizzes."""

    await interaction.response.defer()  # defer reply so you can edit later

    with bot.session as session:
        current_quiz_date = get_current_quiz_date(DAILY_QUIZ_RESET_TIME)

        unique_date = (
            session.query(Quiz.date)
            .filter(Quiz.date >= current_quiz_date)
            .distinct()
            .order_by(Quiz.date)
            .all()
        )

        if not unique_date:
            await interaction.followup.send(
                f"No planned quizzes after {current_quiz_date}.", ephemeral=True
            )
            return

        quiz_types = session.query(QuizType).all()
        pages = []

        for i, quiz_date_row in enumerate(unique_date):
            quiz_date = quiz_date_row[0]
            day_label = f"Today - {quiz_date.strftime('%Y-%m-%d')}" if i == 0 else str(quiz_date)

            embed = discord.Embed(
                title="Planned Quizzes",
                color=0xBBE6F3,
            )

            embed.add_field(
                name=f":calendar_spiral: __**{day_label}**__",
                value="",
                inline=False,
            )

            for j, quiz_type in enumerate(quiz_types):
                quiz = (
                    session.query(Quiz)
                    .filter(Quiz.id_type == quiz_type.id, Quiz.date == quiz_date)
                    .first()
                )

                if quiz:
                    creator_id = quiz.creator_id
                    value = f"> Queued by <@{creator_id}>"
                else:
                    value = "> Unplanned"

                embed.add_field(
                    name=f"> {quiz_type.emoji} {quiz_type.type}",
                    value=value,
                    inline=True,
                )

                if (j + 1) % 2 == 0 and j + 1 != len(quiz_types):
                    embed.add_field(name="", value="", inline=False)

            pages.append(embed)

# ---- Improved FakeContext wrapper for interactions ----
        class FakeContext:
            def __init__(self, interaction: discord.Interaction):
                self.interaction = interaction
                self.author = interaction.user
                self.channel = interaction.channel

            async def send(self, *args, **kwargs):
                """
                Map a ctx.send(...) call to interaction.followup.send(...)
                but don't pass `view` if it's None (discord.py enforces view type).
                Also pass ephemeral when provided.
                """
                # interaction.followup.send requires that 'view' be a View instance if provided.
                # Many callers may pass view=None; drop it to avoid TypeError.
                view = kwargs.pop("view", None)
                # capture ephemeral if present
                ephemeral = kwargs.pop("ephemeral", None)

                followup_kwargs = kwargs.copy()
                if view is not None:
                    followup_kwargs["view"] = view
                if ephemeral is not None:
                    followup_kwargs["ephemeral"] = ephemeral

                return await self.interaction.followup.send(*args, **followup_kwargs)

            # Provide a minimal compatible interface if needed:
            async def fetch_message(self, message_id):
                return await self.interaction.channel.fetch_message(message_id)

        # 2) create FakeContext and pass to paginator
        ctx = FakeContext(interaction)
        paginator = EmbedPaginatorSession(ctx, *pages)
        await paginator.run()

@bot.tree.command(name="equiz")
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
                session.query(UserStartQuizTimestamp).filter(
                    UserStartQuizTimestamp.quiz_id == quiz.id
                ).delete()

                # Commit the deletion to the database
                session.commit()

                await interaction.response.send_message(
                    f"{quiz_type.name} quiz updated for {quiz_date}. "
                    f"buttons for {quiz_type.name} also resetted."
                )
            else:
                await interaction.response.send_message("nothing to clear.")
        if clear_attempts:
            gender_condition_answer = (
                Answer.quiz_id
                if quiz.type.id
                == 1  # 1 represents Male Seiyuu and 2 represents Female Seiyuu
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
                    new_bonus_answer
                    if new_bonus_answer is not None
                    else quiz.bonus_answer
                )

                session.commit()

                await interaction.response.send_message(
                    f"{quiz_type.name} quiz updated for {quiz_date}."
                )
            else:
                await interaction.response.send_message(
                    "please provide one or more of the optional values to update."
                )

# Command to edit answers
@bot.tree.command(name="eanswer")
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

    with bot.session as session:
        if not is_bot_admin(session=session, user=interaction.user):
            await interaction.response.send_message(
                "You are not an admin, you can't use this command."
            )
            return

    # Access the database
    with SessionFactory() as session:
        # Build the query
        query = session.query(Answer).filter_by(user_id=user_id, answer=answer)
        if answer_time is not None:
            query = query.filter_by(answer_time=answer_time)
        answer_obj = query.first()

        # Get the user
        user = (
            get_user(session=session, user=interaction.author, add_if_not_exist=True)
            if not user_id
            else get_user_from_id(session=session, user_id=user_id)
        )
        if not user:
            await interaction.send(
                f"{interaction.author.mention} This person doesn't have any guesses yet."
            )
            return

        # Check if the result is None
        if answer_obj is None:
            await interaction.response.send_message("Answer not found.")
            return

        # Delete the answer if delete is True
        if delete:
            session.delete(answer_obj)
            session.commit()
            await interaction.response.send_message(
                f"Answer for user **{user.name}**, answer {answer}, and time {answer_time} deleted."
            )
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

        await interaction.response.send_message(
            f"Answer for user **{user.name}**, answer {answer}, and time {answer_time} updated."
        )

DATABASE_PATH = "database/poyuta.db"

@bot.tree.command(name="exportdb", description="Export the bot's SQLite database")
async def exportdb(interaction: discord.Interaction):

    with bot.session as session:
        if not is_bot_admin(session=session, user=interaction.user):
            await interaction.response.send_message(
                "You are not an admin, you can't use this command."
            )
            return

    import os
    print("Looking for DB at:", os.path.abspath(DATABASE_PATH))

    if not os.path.exists(DATABASE_PATH):
        return await interaction.response.send_message(
            f"❌ Database file not found at `{DATABASE_PATH}`.",
            ephemeral=True
        )

    file = discord.File(DATABASE_PATH, filename="poyuta_export.db")

    await interaction.response.send_message(
        content="📦 Here's your database export:",
        file=file,
        ephemeral=True
    )

@bot.tree.command(name="importdb", description="Import a SQLite database and replace the current one.")
async def importdb(interaction: discord.Interaction):

    # Admin check
    with bot.session as session:
        if not is_bot_admin(session=session, user=interaction.user):
            return await interaction.response.send_message(
                "You are not an admin, you can't use this command.",
                ephemeral=True
            )

    # Ask for upload
    await interaction.response.send_message(
        "📥 Please upload the **.db** file you want to import.\n"
        "_(Upload it as the next message, this request expires in 60 seconds.)_",
        ephemeral=True
    )

    # Wait for file upload
    def check(msg: discord.Message):
        return (
            msg.author.id == interaction.user.id
            and len(msg.attachments) == 1
        )

    try:
        msg = await bot.wait_for("message", timeout=60, check=check)
    except asyncio.TimeoutError:
        return await interaction.followup.send(
            "⏳ Import timed out. Please use `/importdb` again.",
            ephemeral=True
        )

    attachment = msg.attachments[0]

    # Validate extension
    if not attachment.filename.lower().endswith((".db", ".sqlite", ".sqlite3")):
        return await interaction.followup.send(
            "❌ Invalid file type. Must be a `.db` or `.sqlite` file.",
            ephemeral=True
        )

    # Save uploaded DB temporarily
    temp_path = DATABASE_PATH + ".tmp_import"
    await attachment.save(temp_path)

    # Validate SQLite file
    try:
        conn = sqlite3.connect(temp_path)
        conn.execute("SELECT name FROM sqlite_master LIMIT 1;")
        conn.close()
    except Exception as e:
        os.remove(temp_path)
        return await interaction.followup.send(
            f"❌ Uploaded file is **not** a valid SQLite database:\n```\n{e}\n```",
            ephemeral=True
        )

    # Backup current DB
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{DATABASE_PATH}.backup_{timestamp}"

    try:
        shutil.copy2(DATABASE_PATH, backup_path)
    except Exception as e:
        return await interaction.followup.send(
            f"⚠️ Failed to create backup:\n```\n{e}\n```",
            ephemeral=True
        )

    # Replace DB
    shutil.move(temp_path, DATABASE_PATH)

    await interaction.followup.send(
        "✅ **Database imported successfully!**\n"
        f"A backup was saved as:\n`{backup_path}`\n\n",
        ephemeral=True
    )

# Helper function to check if a user is an admin
def is_bot_admin(session, user):
    try:
        user_obj = session.query(User).filter_by(id=user.id, is_admin=True).first()
        return user_obj is not None
    except Exception as e:
        return False
