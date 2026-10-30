"""The pipeline's data: what the agents read and write, as pydantic models.

    Storyboard    an ad: look, product, shots, titles   (director; pipeline.studio.build renders it)
    BrandProfile  what the photos say about the brand   (brand analyst)
    Critique      a shot's scores and fixes             (critic)
    AdCritique    the whole ad's: cuts, rhythm, arc      (critic)
"""

from .brand import BrandProfile, PartMaterial, Swatch, Typography
from .critique import AdCritique, AdIssue, AdScores, Critique, Issue, Scores
from .storyboard import (Backdrop, CameraMove, Environment, Key, Label, Lighting, Look, PartLook, Pedestal, Product,
                         ProductMotion, ProfilePart, Shot, Storyboard, Surface, Title, Track)

__all__ = [
    "AdCritique", "AdIssue", "AdScores", "Backdrop", "BrandProfile", "CameraMove", "Critique", "Environment", "Issue", "Key", "Label", "Lighting", "Look",
    "PartLook", "PartMaterial", "Pedestal", "Product", "ProductMotion", "ProfilePart", "Scores", "Shot", "Storyboard", "Surface",
    "Swatch", "Title", "Track", "Typography",
]
