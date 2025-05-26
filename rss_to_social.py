import json
import os
import sys
from datetime import datetime
from time import mktime, struct_time

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
                feed_url: datetime.fromtimestamp(iso_date).timetuple()
                for feed_url, iso_date in last_runs.items()
            }

    return last_runs


def load_feed_urls() -> list[str]:
    log.info("Loading feed URLs")

    feed_urls = os.getenv("RSS_FEED_URLS")

    if feed_urls is None:
        log.warning("No feed URLs found in RSS_FEED_URLS")
        sys.exit(2)

    feed_urls = feed_urls.splitlines()

    log.info(f"Feed URLs found: {len(feed_urls)}")

    return feed_urls


def store_last_runs(last_runs: dict[str, struct_time]) -> None:
    log.info("Saving last run dates")

    last_runs_path = os.getenv("LAST_RUNS_PATH")

    if last_runs_path is None:
        log.error("You must set LAST_RUNS_PATH")
        sys.exit(1)

    log.info(f"Wrote last run dates: {last_runs_path}")

    with open(last_runs_path, "w") as fp:
        iso_last_runs = {
            feed_url: mktime(struct_time_date)
            for feed_url, struct_time_date in last_runs.items()
        }
        json.dump(iso_last_runs, fp)


@click.command()
@click.option("--force-latest", click.INT, default=0)
def main(force_latest: int):
    log.info("Running RSS to Social")

    last_runs = load_last_runs()
    feed_urls = load_feed_urls()
    now = datetime.now().timetuple()

    for idx, feed_url in enumerate(feed_urls, 1):
        log.info(f"Parsing feed #{idx}: {feed_url}")

        feed = feedparser.parse(feed_url)
        sorted_entries = sorted(
            feed.entries,
            key=lambda e: e.published_parsed,
            reverse=True,
        )

        new_entries = []

        for n, entry in enumerate(sorted_entries):
            if (
                feed_url not in last_runs
                or n < force_latest
                or entry.published_parsed > last_runs[feed_url]
            ):
                new_entries.append(entry)

        if len(new_entries) > 0:
            log.info(f"Feed #{idx} was updated: processing")
            log.debug(feed)
            last_runs[feed_url] = now
        else:
            log.info(f"Nothing to do for feed #{idx}: skipping")

    store_last_runs(last_runs)

    log.info("Done")


if __name__ == "__main__":
    main()
