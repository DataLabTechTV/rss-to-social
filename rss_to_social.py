import json
import os
import sys
from datetime import datetime
from time import struct_time

import click
import feedparser
from loguru import logger as log


def load_last_runs() -> dict[str, struct_time]:
    log.info("Loading last run dates, if any exist")

    last_runs_path = os.getenv("LAST_RUNS_PATH")

    if last_runs_path is None:
        log.error("You must set LAST_RUNS_PATH")
        sys.exit(1)

    log.info(f"Last runs found: {last_runs_path}")

    last_runs = {}

    if os.path.exists(last_runs_path):
        log.info("Loading previously existing last run dates")

        with open(last_runs_path, "r") as fp:
            last_runs = json.load(fp)
            last_runs = {
                feed_url: datetime.fromisoformat(v).timetuple()
                for feed_url, v in last_runs.items()
            }

    return last_runs


def load_feed_urls() -> list[str]:
    log.info("Loading feed URLs")

    feed_urls = os.getenv("RSS_FEED_URLS")

    if feed_urls is None:
        log.warning("No feed URLs found in RSS_FEED_URLS")
        sys.exit(2)

    log.info(f"Feed URLs found: {len(feed_urls)}")

    return feed_urls.split("\n")


def save_last_runs(last_runs: dict[str, struct_time]) -> None:
    log.info("Saving last run dates")

    last_runs_path = os.getenv("LAST_RUNS_PATH")

    if last_runs_path is None:
        log.error("You must set LAST_RUNS_PATH")
        sys.exit(1)

    log.info(f"Wrote last run dates: {last_runs_path}")

    with open(last_runs_path, "w") as fp:
        json.dump(last_runs, fp)


@click.command()
def main():
    log.info("Running RSS to Social")

    last_runs = load_last_runs()
    feed_urls = load_feed_urls()
    now = datetime.now().timetuple()

    for idx, feed_url in enumerate(feed_urls, 1):
        log.info(f"Parsing feed #{idx}: {feed_url}")

        feed = feedparser.parse(feed_url)

        if last_runs.get(feed_url) is None or last_runs[feed_url] < now:
            print(feed)
            last_runs[feed_url] = now

    save_last_runs()

    log.info("Done")


if __name__ == "__main__":
    main()
