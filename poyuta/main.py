# Standard libraries
import re


# Discord
import discord
from discord import app_commands
from discord.ext import commands

# Database
from poyuta.database import User, Quiz, Answer, SessionFactory


# Utils
from poyuta.utils import (
    load_environment,
    extract_answer_from_user_input,
    process_user_input,
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

# Store game state (current female clip and correct answer)
current_female_clip = "none yet..."
current_male_clip = "none yet..."
correct_female = "?"
correct_male = "?"
admin_user_ids = [
    195534572581158913,
    240181741703266304,
]  # Replace with the admin user IDs
# TODO : define in database ? Possibility to add new admin id from commands ?


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


# 'newquiz' command
@bot.tree.command(name="newquiz")
@app_commands.describe(new_female_clip="input new clip for female")
async def newquiz(
    interaction: discord.Interaction,
    new_female_clip: str,
    new_correct_female: str,
    new_male_clip: str,
    new_correct_male: str,
):
    user = None

    # Get the user, including the 'answers' relationship
    with bot.session as session:
        user = (
            session.query(User).filter(User.discord_id == interaction.user.id).first()
        )

    if not user:
        with bot.session as session:
            print(
                "adding user to database:", interaction.user.id, interaction.user.name
            )
            user = User(discord_id=interaction.user.id, name=interaction.user.name)
            session.add(user)
            session.commit()

    if interaction.user.id not in admin_user_ids:
        await interaction.response.send_message(f"only admins can change the clips")
    else:
        await change_female(new_female_clip, new_correct_female)
        await change_male(new_male_clip, new_correct_male)
        await interaction.response.send_message(f"clips updated")
        # Get the user, including the 'answers' relationship
        with bot.session as session:
            quiz_edit = Quiz(
                female_clip=new_female_clip,
                female_answer=new_correct_female,
                male_clip=new_male_clip,
                male_answer=new_correct_male,
            )
            session.add(quiz_edit)
            session.commit()

        print("adding quiz to database:", interaction.user.id, interaction.user.name)


# Define the quiz ID (assuming it's the same for both female and male quizzes)
quiz_id = 1  # You should replace this with the actual quiz ID


# Modify the 'female' command
@bot.tree.command(name="female")
@app_commands.describe(seiyuu_female="guess the female seiyuu")
async def female(interaction: discord.Interaction, seiyuu_female: str):
    user_answer_pattern = process_user_input(seiyuu_female)
    if re.search(user_answer_pattern, correct_female):
        await interaction.response.send_message(
            f"you guessed it **correctly** :muscle:"
        )

        # Store the user's answer in the database using the Answer table
        with bot.session as session:
            user = (
                session.query(User)
                .filter(User.discord_id == interaction.user.id)
                .first()
            )
            if user:
                user_answer = Answer(
                    user_id=interaction.user.id,
                    quiz_id=quiz_id,
                    answer=seiyuu_female,
                    answer_type="female",
                    is_correct=True,
                )
                session.add(user_answer)
                session.commit()
    else:
        await interaction.response.send_message(f"**incorrect** :skull:")
        with bot.session as session:
            user = (
                session.query(User)
                .filter(User.discord_id == interaction.user.id)
                .first()
            )
            if user:
                user_answer = Answer(
                    user_id=interaction.user.id,
                    quiz_id=quiz_id,
                    answer=seiyuu_female,
                    answer_type="female",
                    is_correct=False,
                )
                session.add(user_answer)
                session.commit()


# Modify the 'male' command similarly
@bot.tree.command(name="male")
@app_commands.describe(seiyuu_male="guess the male seiyuu")
async def male(interaction: discord.Interaction, seiyuu_male: str):
    user_answer_pattern = process_user_input(seiyuu_male)
    if re.search(user_answer_pattern, correct_male):
        await interaction.response.send_message(
            f":fearful: you guessed it **correctly**"
        )

        # Store the user's answer in the database using the Answer table
        with bot.session as session:
            user = (
                session.query(User)
                .filter(User.discord_id == interaction.user.id)
                .first()
            )
            if user:
                user_answer = Answer(
                    user_id=interaction.user.id,
                    quiz_id=quiz_id,
                    answer=seiyuu_male,
                    answer_type="male",
                    is_correct=True,
                )
                session.add(user_answer)
                session.commit()
    else:
        await interaction.response.send_message(f"**incorrect** :skull:")
        with bot.session as session:
            user = (
                session.query(User)
                .filter(User.discord_id == interaction.user.id)
                .first()
            )
            if user:
                user_answer = Answer(
                    user_id=interaction.user.id,
                    quiz_id=quiz_id,
                    answer=seiyuu_male,
                    answer_type="male",
                    is_correct=False,
                )
                session.add(user_answer)
                session.commit()
