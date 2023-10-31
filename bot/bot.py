# third party imports
import discord
from discord.ext import commands

# Internal imports
from utils import load_environment


config = load_environment()

intents = discord.Intents.all()
intents.reactions = True
intents.messages = True

bot = commands.Bot(command_prefix="err ", intents=intents)

# Define a dictionary to store reaction roles
reaction_roles = {
    "❤️": 1168130056497942549,  # Emote and Role ID for the first role
    "👍": 1168196460324593744,  # Emote and Role ID for the second role
    # You can initially set up some default emotes and roles
}


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")


@bot.event
async def on_raw_reaction_add(payload):
    if payload.guild_id == 366643056138518529 and str(payload.emoji) in reaction_roles:
        role_id = reaction_roles[str(payload.emoji)]
        role = discord.utils.get(payload.member.guild.roles, id=role_id)
        await payload.member.add_roles(role)


@bot.event
async def on_raw_reaction_remove(payload):
    if payload.guild_id == 366643056138518529 and str(payload.emoji) in reaction_roles:
        role_id = reaction_roles[str(payload.emoji)]
        role = discord.utils.get(bot.get_guild(payload.guild_id).roles, id=role_id)
        member = bot.get_guild(payload.guild_id).get_member(payload.user_id)
        await member.remove_roles(role)


@bot.command()
async def roles(ctx):
    # Create an embed
    embed = discord.Embed(
        title="Quiz Roles",
        description="React to get a role:",
        color=0xBBE6F3,  # You can set the color of the embed here
    )

    for emote, role_id in reaction_roles.items():
        role = ctx.guild.get_role(role_id)
        if role:
            embed.add_field(name=emote, value=f"<@&{role_id}>", inline=True)

    embed.add_field(
        name="Additional Information",
        value="You can add more details here.",
        inline=False,
    )

    embed.set_author(name="nayuta", icon_url="https://i.imgur.com/lR3Gshd.png")

    embed.set_footer(text=" --- ", icon_url="https://i.imgur.com/0NSQW44.png")

    embed.set_image(url="https://i.imgur.com/QeMw2PV.png")

    message = await ctx.send(embed=embed)

    for emote in reaction_roles:
        await message.add_reaction(emote)


@bot.command()
async def addrole(ctx, emote, role: discord.Role):
    # Check if the user has permission to add reaction roles
    if not ctx.author.guild_permissions.manage_roles:
        await ctx.send("You don't have the required permissions to add reaction roles.")
        return

    # Check if the emote is valid
    try:
        await ctx.message.add_reaction(emote)
    except Exception as e:
        await ctx.send(f"Invalid emote: {e}")
        return

    # Add the emote and role to the dictionary
    reaction_roles[emote] = role.id
    await ctx.send(f"Reaction role added: {emote} -> {role.mention}")


# Define a list of correct answers
correct_answers = ['correct answer 1', 'correct answer 2']

@bot.event
async def on_message(message):
    if message.channel.id == 1168221032516161626 and '||' in message.content:
        # Process the user's input
        await process_user_input(message)
    await bot.process_commands(message)


async def process_user_input(message):
    user_response = message.content[len('||'):]  # Remove the catchphrase prefix
    await check_and_react(user_response, message)

async def check_and_react(user_response, message):
    user_response = user_response.lower()
    user_response = user_response.replace("||", "").strip()
    
    if any(answer in user_response for answer in correct_answers):
        await message.add_reaction("✅")  # React with a correct emote
    else:
        await message.add_reaction("❌")  # React with an incorrect emote


# Run your bot with your bot token
bot.run(config["BOT_SECRET_TOKEN"])
