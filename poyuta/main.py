# Standard libraries
import re


# Discord
import discord
from discord import app_commands
from discord.ext import commands

# Database
from poyuta.database import User, Quiz, Answer, SessionFactory


# Utils
from poyuta.utils import load_environment, process_user_input


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

    with bot.session as session:
        user = session.query(User).filter(User.id == interaction.user.id).first()

        if not user:
            user = User(id=interaction.user.id, name=interaction.user.name)
            session.add(user)
            session.commit()

    if interaction.user.id not in admin_user_ids:
        await interaction.response.send_message("only admins can change the clips")
    else:
        await change_female(new_female_clip, new_correct_female)
        await change_male(new_male_clip, new_correct_male)
        await interaction.response.send_message("clips updated")

        with bot.session as session:
            new_quiz = Quiz(
                female_clip=new_female_clip,
                female_answer=new_correct_female,
                male_clip=new_male_clip,
                male_answer=new_correct_male,
            )
            session.add(new_quiz)
            session.commit()


# Define the quiz ID (assuming it's the same for both female and male quizzes)
quiz_id = 1  # You should replace this with the actual quiz ID


@bot.tree.command(name="female")
@app_commands.describe(seiyuu="guess the female seiyuu")
async def female(interaction: discord.Interaction, seiyuu: str):
    """Guess the seiyuu for the current female clip."""

    # retrieve user from database, and add it if it doesn't exist
    with bot.session as session:
        user = session.query(User).filter(User.id == interaction.user.id).first()

        if not user:
            user = User(id=interaction.user.id, name=interaction.user.name)
            session.add(user)
            session.commit()

    # create the answer object
    user_answer = Answer(
        user_id=user.id,
        quiz_id=quiz_id,
        answer=seiyuu,
        answer_type="female",
    )

    # Generate a pattern to match with the correct answer
    user_answer_pattern = process_user_input(seiyuu)

    # If the pattern matches : the answer is correct
    if re.search(user_answer_pattern, correct_female):
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

    # retrieve user from database, and add it if it doesn't exist
    with bot.session as session:
        user = session.query(User).filter(User.id == interaction.user.id).first()

        if not user:
            user = User(id=interaction.user.id, name=interaction.user.name)
            session.add(user)
            session.commit()

    # create the answer object
    user_answer = Answer(
        user_id=user.id,
        quiz_id=quiz_id,
        answer=seiyuu,
        answer_type="male",
    )

    # Generate a pattern to match with the correct answer
    user_answer_pattern = process_user_input(seiyuu)

    # If the pattern matches : the answer is correct
    if re.search(user_answer_pattern, correct_male):
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
