"""
Utility functions for the bot.
"""

# Standard library imports
import os

# Third party imports
from dotenv import dotenv_values


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
