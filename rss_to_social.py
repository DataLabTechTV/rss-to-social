import os
import sys

import click
import feedparser
from loguru import logger as log


@click.command()
def main():
    log.info("Here are some env vars:")
    feed_urls = os.getenv("RSS_FEED_URLS")

    if feed_urls is None:
        log.warning("No feed URLs found in RSS_FEED_URLS")
        sys.exit(1)

    for idx, feed_url in enumerate(feed_urls.split("\n"), 1):
        log.info(f"Parsing feed #{idx}: {feed_url}")

        feed = feedparser.parse(feed_url)
        print(feed)


if __name__ == "__main__":
    main()
