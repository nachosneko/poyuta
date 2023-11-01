# Standard libraries
import re


# Discord
import discord
from discord import app_commands
from discord.ext import commands

# Database
from poyuta.database import User, SessionFactory

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


@bot.command()
async def newfemale(ctx, new_female_clip, new_correct_female):
    print(ctx.author.id)

    # example usage for adding a user to the database
    # get current user
    with bot.session as session:
        user = session.query(User).filter(User.discord_id == ctx.author.id).first()

    # if user doesn't exist, add them to the database
    if not user:
        with bot.session as session:
            print("adding user to database:", ctx.author.id, ctx.author.name)
            # add it and keep the user object
            user = User(discord_id=ctx.author.id, name=ctx.author.name)
            session.add(user)
            session.commit()

    # example accessing all answers from users (they aren't added to the database yet, so it's empty, but you get the idea)
    # you can access directly from answers attribute because of relationship defined in database.py (back_populates)
    with bot.session as session:
        user = session.query(User).filter(User.discord_id == ctx.author.id).first()
        print(user)
        print(user.answers)

    if ctx.author.id not in admin_user_ids:
        await ctx.send("only admins can change the clip")
    else:
        await change_female(new_female_clip, new_correct_female)
        await ctx.send(f"female clip updated")


@bot.command()
async def newmale(ctx, new_male_clip, new_correct_male):
    if ctx.author.id not in admin_user_ids:
        await ctx.send("only admins can change the clip")
    else:
        await change_male(new_male_clip, new_correct_male)
        await ctx.send(f"male clip updated")


@bot.tree.command(name="female")
@app_commands.describe(seiyuu_female="guess the female seiyuu")
async def female(interaction: discord.Interaction, seiyuu_female: str):
    user_answer_pattern = process_user_input(seiyuu_female)
    if re.search(user_answer_pattern, correct_female):
        await interaction.response.send_message(
            f"you guessed it **correctly** :muscle:"
        )
    else:
        await interaction.response.send_message(f"**incorrect** :skull:")


@bot.tree.command(name="male")
@app_commands.describe(seiyuu_male="guess the male seiyuu")
async def male(interaction: discord.Interaction, seiyuu_male: str):
    user_answer_pattern = process_user_input(seiyuu_male)
    if re.search(user_answer_pattern, correct_male):
        await interaction.response.send_message(
            f":fearful: you guessed it **correctly**"
        )
    else:
        await interaction.response.send_message(f"**incorrect** :skull:")
