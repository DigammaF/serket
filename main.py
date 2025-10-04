
import logging
import logging.handlers

from pathlib import Path

BASE = Path(__file__).parent.resolve()
LOGS = BASE/"logs"

if not LOGS.exists(): LOGS.mkdir()

root = logging.getLogger()
root.handlers.clear()

file_handler = logging.handlers.RotatingFileHandler(
	LOGS/"serket.log", mode="a", encoding="utf-8",
	maxBytes=100_000, backupCount=10
)
file_handler.setFormatter(logging.Formatter(
	style="{",
	fmt="{levelname} [{asctime}] {filename}@{lineno} - {name}: {message}"
))
root.addHandler(file_handler)
root.setLevel(logging.INFO)

from core.context import Context

logger = logging.getLogger("serket")

def main():
	try:
		logger.info("starting the main loop")
		Context().mainloop()

	except:
		print(f"Oh nyo! Something went terribly wrong. Pwease see logs :3 ({LOGS})")
		logger.exception("An exception occured")

if __name__ == "__main__":
	main()
