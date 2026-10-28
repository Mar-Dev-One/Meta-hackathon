"""Failures come back as MetaError with the server's own message, and
nothing is cached for them."""

from _common import report

from pipeline.meta import MetaError, spark


def run() -> dict:
    try:
        spark.ask("hello", model="muse-spark-9.9", cache_ok=False)
    except MetaError as e:
        return {"bad model": str(e)[:200], "status": e.status}
    raise AssertionError("a model that doesn't exist answered")


if __name__ == "__main__":
    report(run())
