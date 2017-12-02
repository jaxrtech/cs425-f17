import os
from os.path import join, dirname
from pathlib import Path

from dotenv import load_dotenv

dotenv_path = join(dirname(__file__), '.env')
if not Path(dotenv_path).is_file():
    raise FileNotFoundError(dotenv_path)

load_dotenv(dotenv_path)

DB_NAME = os.environ.get("DB_NAME")
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_HOST = os.environ.get("DB_HOST")
DB_PORT = os.environ.get("DB_PORT")
