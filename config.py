import databases
from starlette.config import Config
from starlette.datastructures import CommaSeparatedStrings, Secret


config = Config(".env")


DEBUG = config('DEBUG', cast=bool, default=False)
DATABASE_URL = config('DATABASE_URL', cast=databases.DatabaseURL, default='sqlite:////tmp/db.sqlite')

CORS_ORIGIN = config('CORS_ORIGIN', cast=CommaSeparatedStrings, default='*' if DEBUG else 'None')
ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=CommaSeparatedStrings, default='')
SECRET_KEY = config('SECRET_KEY', cast=Secret, default='Change me')
YOUTUBE_KEY = config('YOUTUBE_KEY', cast=Secret, default='')


# Database tools
DATABASE = databases.Database(str(DATABASE_URL).replace('postgres://', 'postgresql://'))


# Debug run settings
RUN_ADDR = config('RUN_ADDR', cast=str, default='0.0.0.0')
RUN_PORT = config('RUN_PORT', cast=int, default=8000)
