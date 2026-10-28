"""Muse Spark, plain text: does the key work, and what one answer costs."""

from _common import report

from pipeline.meta import spark, usage


def run() -> dict:
    r = spark.ask("In two sentences: what makes a luxury perfume advert feel luxurious on screen?")
    last = usage.calls()[-1]
    return {"cached": r.cached, "seconds": last.seconds,
            "tokens": f"in {last.input_tokens}, out {last.output_tokens}", "cost": f"${last.cost:.5f}",
            "answer": r.text}


if __name__ == "__main__":
    report(run())
