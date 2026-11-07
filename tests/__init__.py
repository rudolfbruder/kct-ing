import os

# Tests never read the developer's .env.
os.environ["KCT_ENV_FILE"] = ""
