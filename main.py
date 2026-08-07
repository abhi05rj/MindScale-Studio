from dataclasses import asdict
from pprint import pprint

from app.content_engine import ContentScoringEngine, ContentStrategyEngine, PinterestFormatter


def build_content_package(topic: str) -> dict:
    strategy = ContentStrategyEngine().create_strategy(topic)
    pinterest_content = PinterestFormatter().format(strategy)
    scores = ContentScoringEngine().score(strategy)

    return {
        "topic": topic,
        "strategy": asdict(strategy),
        "pinterest": pinterest_content,
        "scores": asdict(scores),
    }


if __name__ == "__main__":
    print("MindScale Content Intelligence Engine")
    print("=" * 38)
    pprint(build_content_package("Universe"), sort_dicts=False)
