"""The pipeline's data: what the agents read and write, as pydantic models.

    Storyboard    an ad: look, product, shots, titles   (director; pipeline.studio.build renders it)
    BrandProfile  what the photos say about the brand   (brand analyst)
    Critique      a shot's scores and fixes             (critic)
"""

from .brand import BrandProfile, PartMaterial, Swatch, Typography
from .critique import Critique, Issue, Scores
from .storyboard import (Backdrop, CameraMove, Environment, Key, Label, Lighting, Look, PartLook, Pedestal, Product,
                         ProfilePart, Shot, Storyboard, Title, Track)

__all__ = [
    "Backdrop", "BrandProfile", "CameraMove", "Critique", "Environment", "Issue", "Key", "Label", "Lighting", "Look",
    "PartLook", "PartMaterial", "Pedestal", "Product", "ProfilePart", "Scores", "Shot", "Storyboard", "Swatch",
    "Title", "Track", "Typography",
]
