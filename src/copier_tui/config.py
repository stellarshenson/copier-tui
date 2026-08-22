from pathlib import Path
import sys

from dotenv import load_dotenv
from loguru import logger

########### SETUP ###############

# set up logger
logger.remove()
logger.add(sys.stdout, colorize=True)

########## VARIABLES ############

# Load environment variables from .env file if it exists
load_dotenv()

# paths
PROJ_ROOT = Path(__file__).resolve().parents[2]

# log current root dir
logger.info(f"PROJ_ROOT path is: {PROJ_ROOT}")
