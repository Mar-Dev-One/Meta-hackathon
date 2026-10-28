"""The Meta models, as the agents call them: Muse Spark (text, vision, JSON,
tools; Muse Spark Open with provider="baseten"), SAM 3.1, Muse Image and Muse
Voice Transcribe. Every call is cached on disk by its request (rerunning
costs nothing), retried on rate limits and transient errors, and recorded in
`usage` with its tokens and cost. Failures raise MetaError.

    from pipeline.meta import spark, sam, image, voice, usage
"""

from . import config, image, sam, spark, usage, voice
from .client import MetaError
from .config import MissingKey

__all__ = ["config", "image", "sam", "spark", "usage", "voice", "MetaError", "MissingKey"]
