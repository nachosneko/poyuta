"""
Utility functions for the bot.
"""

# Standard library imports
import os
import re
import numpy as np
from datetime import datetime, date, time, timedelta

# Discord.py
from discord import app_commands, Embed, Interaction, Member
from discord.ext import commands

# Third party imports
from dotenv import dotenv_values

# Database models
from poyuta.database import Quiz, QuizType, Answer, User

# Typing helpers
from sqlalchemy.orm.session import Session
from typing import List, Tuple

# Define a list of replacement rules
ANIME_REGEX_REPLACE_RULES = [
    # Ļ can't lower correctly with sql lower function
    {"input": "ļ", "replace": "[ļĻ]"},
    {"input": "l", "replace": "[l˥ļĻΛ]"},
    # Ź can't lower correctly with sql lower function
    {"input": "ź", "replace": "[źŹ]"},
    {"input": "z", "replace": "[zźŹ]"},
    {"input": "ou", "replace": "(ou|ō|o)"},
    {"input": "oo", "replace": "(oo|ō|o)"},
    {"input": "oh", "replace": "(oh|ō|o)"},
    {"input": "wo", "replace": "(wo|o)"},
    {"input": "o", "replace": "([oōóòöôøӨΦο]|ou|oo|oh|wo)"},
    {"input": "uu", "replace": "(uu|u|ū)"},
    {"input": "u", "replace": "([uūûúùüǖμ]|uu)"},
    {"input": "aa", "replace": "(aa|a)"},
    {"input": "ae", "replace": "(ae|æ)"},
    {"input": "a", "replace": "([aäãά@âàáạåæā∀Λ]|aa)"},
    {"input": "c", "replace": "[cςč℃Ↄ]"},
    # É can't lower correctly with sql lower function
    {"input": "é", "replace": "[éÉ]"},
    {"input": "e", "replace": "[eəéÉêёëèæē]"},
    {"input": "'", "replace": "['’ˈ]"},
    {"input": "n", "replace": "[nñ]"},
    {"input": "0", "replace": "[0Ө]"},
    {"input": "2", "replace": "[2²]"},
    {"input": "3", "replace": "[3³]"},
    {"input": "5", "replace": "[5⁵]"},
    {"input": "*", "replace": "[*✻＊✳︎]"},
    {
        "input": " ",
        "replace": "( ?[²³⁵★☆♥♡\\/\\*✻✳︎＊'ˈ-∽~〜・·\\.,;:!?@_-⇔→≒=\\+†×±◎Ө♪♩♣␣∞] ?| )",
    },
    {"input": "i", "replace": "([iíίɪ]|ii)"},
    {"input": "x", "replace": "[x×]"},
    {"input": "b", "replace": "[bßβ]"},
    {"input": "r", "replace": "[rЯ]"},
    {"input": "s", "replace": "[sς]"},
]


def load_environment() -> dict:
    """Load environment variables from .env files and the environment.
    Load in that order :
    - .env.shared
    - .env.secret
    - environment variables

    The latest loaded variables override the previous ones.

    Returns
    -------
        dict: The environment variables.
    """

    config = {
        **dotenv_values(".env.shared"),  # load shared development variables
        **dotenv_values(".env.secret"),  # load sensitive variables
        **os.environ,  # override loaded values with environment variables
    }

    return config


def escape_and_replace(input_str: str) -> str:
    """Escape special characters and replace specific sequences.

    Parameters
    ----------
    input_str : str
        String to escape and replace.

    Returns
    -------
    str
        Escaped and replaced string.
    """

    escaped_str = re.escape(input_str)
    escaped_str = escaped_str.replace(r"\ ", " ")
    escaped_str = escaped_str.replace(r"\*", "*")
    return escaped_str


def apply_regex_rules(input_str: str) -> str:
    """Apply replacement rules using compiled regular expressions.

    Parameters
    ----------
    input_str : str
        String to apply replacement rules to.

    Returns
    -------
    str
        String with replacement rules applied.
    """

    output_str = input_str
    for rule in ANIME_REGEX_REPLACE_RULES:
        pattern = re.compile(re.escape(rule["input"]), re.IGNORECASE)
        output_str = pattern.sub(rule["replace"], output_str)
    return output_str


def generate_regex_pattern(input_str: str, partial_match: bool = True) -> str:
    """Generate a regex pattern for a string.
    Uses the rules defined in ANIME_REGEX_REPLACE_RULES.

    Parameters
    ----------
    input_str : str
        String to generate regex pattern for.

    partial_match : bool, optional
        Whether to match the whole string or not, by default True

    Returns
    -------
    str
        Regex pattern.
    """

    # Escape and replace special characters
    input_str = escape_and_replace(input_str.lower())

    # Apply replacement rules
    ouput_str = apply_regex_rules(input_str)

    # Allow partial match or not
    ouput_str = f".*{ouput_str}.*" if partial_match else f"^{ouput_str}$"

    return ouput_str


def process_user_input(
    input_str: str, partial_match: bool = True, swap_words: bool = True
) -> str:
    """Generate a regex pattern for a string.
    Uses the rules defined in ANIME_REGEX_REPLACE_RULES.

    Parameters
    ----------
    input_str : str
        String to generate regex pattern for.

    partial_match : bool, optional
        Whether to match the whole string or not, by default True

    swap_words : bool, optional
        Whether to allow to swap the order of the words or not, by default True
        Will allow to swap the order of the words if there are exactly two words.

    Returns
    -------
    str
        Regex pattern.
    """

    # Generate the regex pattern
    output_str = generate_regex_pattern(input_str, partial_match=partial_match)

    # if swap_words is False, or there isn't exactly two words, return the pattern
    if not swap_words or len(input_str.split(" ")) != 2:
        return output_str

    # else generate the pattern for the swapped user input, and return the pattern combined with the original pattern
    swapped_input_str = " ".join(input_str.split(" ")[::-1])
    swapped_output_str = generate_regex_pattern(
        swapped_input_str, partial_match=partial_match
    )
    output_str = f"({output_str})|({swapped_output_str})"

    return output_str


async def is_server_admin(ctx: commands.Context, session: Session):
    """Check if a user is a server admin.

    Parameters
    ----------
    ctx : commands.Context
        Context of the command.

    session : Session
        Database session.

    Returns
    -------
    bool
        Whether the user is an admin or not.
    """
    return is_bot_admin(session, ctx.author) or (
        isinstance(ctx.author, Member) and ctx.author.guild_permissions.administrator
    )


def is_bot_admin(session: Session, user: User):
    """Check if a user is a bot admin.

    Parameters
    ----------
    session : Session
        Database session.

    user : User
        User to check.

    Returns
    -------
    bool
        Whether the user is a bot admin or not.
    """

    admins = session.query(User).filter(User.is_admin).all()

    return user.id in [admin.id for admin in admins]


def get_current_quiz_date(daily_quiz_reset_time: time) -> date:
    """Get the current quiz date.
    The current quiz date is yesterday if it's before the daily quiz reset time,
    else it's today.

    Parameters
    ----------
    daily_quiz_reset_time : time
        Time at which the daily quiz resets. HH:MM:SS format.

    Returns
    -------
    date
        Current quiz date.
    """

    # get time now
    now = datetime.now()

    # today's quiz is yesterday date if it's before the daily quiz reset time
    # else it's today's date
    return (
        now.date()
        if now.time() >= daily_quiz_reset_time
        else now.date() - timedelta(days=1)
    )


def reconstruct_discord_pfp_url(user_id: int, pfp_hash: str) -> str:
    """Reconstruct the discord pfp url from the user ID and pfp hash.

    Parameters
    ----------
    user_id : int
        Discord user ID.

    pfp_hash : str
        Discord pfp hash.

    Returns
    -------
    str
        Discord pfp url.
    """

    return f"https://cdn.discordapp.com/avatars/{user_id}/{pfp_hash}.png?size=1024"


def extract_hash_from_discord_pfp_url(pfp_url: str) -> str:
    """Extract the hash from a discord pfp url.

    Parameters
    ----------
    pfp_url : str
        Discord pfp url.

    Returns
    -------
    str
        Hash.
    """

    # https://cdn.discordapp.com/avatars/240181741703266304/545642146415.png?size=1024

    return pfp_url.split("/")[-1].split(".")[0]


def get_user(
    session: Session,
    user: Interaction.user,
    add_if_not_exist: bool = True,
):
    """Get the user from the database from its discord ID.

    Parameters
    ----------
    session : Session
        Database session.

    user : Interaction.user
        Discord user.

    add_if_not_exist : bool, optional
        Whether to add the user to the database if it doesn't exist, by default True.

    Returns
    -------
    User
        User from the database.

    Notes
    -----
    This function first tries to get the user from the database using their Discord ID. If the user is not found and
    `add_if_not_exist` is True, a new user is created in the database with the given ID, name, and profile picture hash.
    If the user is found or added, their profile picture hash is updated if it has changed since the last time they were
    retrieved from the database.
    """

    # extract pfp hash from discord pfp url
    pfp_hash = extract_hash_from_discord_pfp_url(user.avatar.url)

    # try to get the user from the database
    db_user = session.query(User).filter(User.id == user.id).first()

    # add user if it doesn't exist and add_if_not_exist is True
    if not db_user and add_if_not_exist:
        db_user = User(
            id=user.id,
            name=user.name,
            pfp=pfp_hash,
            is_admin=False,
        )
        session.add(db_user)
        session.commit()

    # update pfp if it changed
    if db_user.pfp != pfp_hash:
        db_user.pfp = pfp_hash
        session.commit()

    return db_user


def get_user_from_id(session: Session, user_id: int):
    """Get the user from the database from its discord ID.

    Parameters
    ----------
    session : Session
        Database session.

    user_id : int
        Discord user ID.

    Returns
    -------
    User
        User from the database.
    """

    return session.query(User).filter(User.id == user_id).first()


def get_quiz_type_choices(session: Session) -> List[Tuple[int, str]]:
    """
    Get the quiz type choices.

    This function queries the database session to get a list of distinct quiz types,
    and returns a list of tuples containing the quiz type ID and name.

    Parameters
    ----------
    session : Session
        The database session.

    Returns
    -------
    list[tuple[int, str]]
        A list of tuples containing the quiz type ID and name.
    """

    quiz_types = session.query(QuizType).distinct().all()

    return [
        app_commands.Choice(value=quiz_type.id, name=quiz_type.type)
        for quiz_type in quiz_types
    ]
