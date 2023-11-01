import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Bot
from discord.ext import tasks
import random
import asyncio
import sqlite3

from utils import load_environment

config = load_environment()

intents = discord.Intents.all()
intents.reactions = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)


# Store game state (current female clip and correct answer)
current_female_clip = "none yet..."
current_male_clip = "none yet..."
correct_female = "?"
correct_male = "?"
admin_user_ids = [195534572581158913]  # Replace with the admin user IDs


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
@app_commands.describe(seiyuu_female ="guess the female seiyuu")
async def female(interaction: discord.Interaction, seiyuu_female: str):
    if seiyuu_female.lower() == correct_female.lower():
        await interaction.response.send_message(f"you guessed it **correctly** :muscle:")
    else:
        await interaction.response.send_message(f"**incorrect** :skull:")

@bot.tree.command(name="male")
@app_commands.describe(seiyuu_male ="guess the male seiyuu")
async def male(interaction: discord.Interaction, seiyuu_male: str):
    if seiyuu_male.lower() == correct_male.lower():
        await interaction.response.send_message(f":fearful: you guessed it **correctly**")
    else:
        await interaction.response.send_message(f"**incorrect** :skull:")

# Run the bot with your token
bot.run(config["BOT_SECRET_TOKEN"])
