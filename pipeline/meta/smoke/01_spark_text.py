"""Muse Spark, plain text over the Responses API: does the key work, how fast, what usage looks like."""

from _common import SPARK, meta_client, report, save_json, timed


def run() -> dict:
    client = meta_client()
    with timed() as t:
        response = client.responses.create(
            model=SPARK,
            input="In two sentences: what makes a luxury perfume advert feel luxurious on screen?",
        )
    save_json("01_spark_text.json", response.model_dump())
    usage = response.usage
    return {
        "latency_s": t.seconds,
        "tokens": f"in {usage.input_tokens}, out {usage.output_tokens}" if usage else "?",
        "answer": response.output_text,
    }


if __name__ == "__main__":
    report(run())
