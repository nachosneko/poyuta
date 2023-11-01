"""
Runner for the application
python runner.py
"""

# Internal imports
from poyuta.utils import load_environment
from poyuta.main import bot

config = load_environment()

if __name__ == "__main__":
    bot.run(config["BOT_SECRET_TOKEN"])
