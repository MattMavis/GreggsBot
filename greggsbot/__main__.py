import logging
import os
import sys

from dotenv import load_dotenv

from .config import Config, ConfigError


def setup_logging():
    os.makedirs("log", exist_ok=True)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler("log/out.log", encoding="utf-8")],
    )


def main():
    if os.path.exists("environment.env"):
        load_dotenv("environment.env")
    try:
        config = Config()
    except ConfigError as e:
        sys.exit(str(e))

    setup_logging()
    from .bot import GreggsBot

    GreggsBot(config).run(config.token, log_handler=None)


if __name__ == "__main__":
    main()
