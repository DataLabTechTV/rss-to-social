import json
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import mktime, struct_time
from typing import Optional, Self

import atproto
import click
import feedparser
import requests
from atproto.exceptions import AtProtocolError
from feedparser import FeedParserDict
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


def load_feed_urls() -> list[str]:
    log.info("Loading feed URLs")

    feed_urls = os.getenv("RSS_FEED_URLS")

    if feed_urls is None:
        log.warning("No feed URLs found in RSS_FEED_URLS")
        sys.exit(2)

    feed_urls = feed_urls.splitlines()

    log.info(f"Feed URLs found: {len(feed_urls)}")

    return feed_urls


def load_active_socials() -> set[str]:
    log.info("Loading active socials")

    active_socials = os.getenv("ACTIVE_SOCIALS")

    if active_socials is None:
        log.warning("No active socials found in ACTIVE_SOCIALS")
        sys.exit(2)

    active_socials = active_socials.splitlines()

    log.info(f"Active socials found: {', '.join(active_socials)}")

    return set(active_socials)


def download_image(url: str) -> Path:
    response = requests.get(url)
    response.raise_for_status()

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        path = Path(tmp.name)

    with open(path, "wb") as f:
        f.write(response.content)

    return path


@dataclass
class Post:
    title: str
    description: str
    link: Optional[str] = None
    image_path: Optional[str] = None
    image_alt: Optional[str] = None

    @classmethod
    def from_entry(cls, entry: FeedParserDict) -> Self:
        post = cls(
            title=entry.title,
            description=entry.summary,
        )

        post.link = entry.link

        if "media_content" in entry and len(entry.media_content) > 0:
            img_url = entry.media_content[0].get("url")

            if img_url is not None:
                post.image_path = download_image(img_url)
                post.image_alt = f"{entry.title} Thumbnail"

        return post

    def __del__(self):
        if self.image_path is not None and self.image_path.exists():
            try:
                self.image_path.unlink()
                log.info(f"Post temporary image deleted: {self.image_path}")
            except Exception:
                log.warning(f"Failed to delete post temporary image: {self.image_path}")


def post_to_bluesky(post: Post) -> None:
    log.info("Posting to Bluesky")

    bsky_user = os.getenv("BSKY_USERNAME")

    if bsky_user is None:
        log.error("Could not post to Bluesky: BSKY_USERNAME not set")
        return False

    bsky_pass = os.getenv("BSKY_PASSWORD")

    if bsky_pass is None:
        log.error("Could not post to Bluesky: BSKY_PASSWORD not set")
        return False

    try:
        client = atproto.Client(base_url="https://bsky.social")
        client.login(bsky_user, bsky_pass)

        record = {
            "$type": "app.bsky.feed.post",
            "text": f"{post.title} - {post.description}",
            "createdAt": client.get_current_time_iso(),
        }

        log.debug(f"Bluesky post image path: {post.image_path}")
        if post.image_path is not None:
            with open(post.image_path, "rb") as fp:
                image_data = fp.read()

            uploaded_image = client.com.atproto.repo.upload_blob(image_data)
            embed = {
                "$type": "app.bsky.embed.external",
                "external": {
                    "uri": post.link,
                    "title": post.title,
                    "description": post.description,
                },
            }

            if uploaded_image.blob:
                embed["external"]["thumb"] = uploaded_image.blob

            record |= {"embed": embed}

        client.app.bsky.feed.post.create(
            repo=client.me.did,
            record=record,
        )
    except AtProtocolError as e:
        log.exception("Couldn't post to Bluesky")


@click.command()
@click.option("--force-latest", type=click.INT, default=0)
def main(force_latest: int):
    log.info("Running RSS to Social")

    last_runs = load_last_runs()
    feed_urls = load_feed_urls()
    active_socials = load_active_socials()
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

        if feed_url not in last_runs:
            log.info(f"No previous runs found for: {feed_url}")

        if force_latest > 0:
            log.info(f"Forcing re-post for {force_latest} most recent entries")

        for n, entry in enumerate(sorted_entries):
            if (
                feed_url not in last_runs
                or n < force_latest
                or entry.published_parsed > last_runs[feed_url]
            ):
                new_entries.append(entry)

        if len(new_entries) > 0:
            log.info(f"Feed #{idx} was updated: processing")

            for entry in new_entries:
                post = Post.from_entry(entry)

                if "bluesky" in active_socials:
                    post_to_bluesky(post)

            last_runs[feed_url] = now
        else:
            log.info(f"Nothing to do for feed #{idx}: skipping")

    store_last_runs(last_runs)

    log.info("Done")


if __name__ == "__main__":
    main()
