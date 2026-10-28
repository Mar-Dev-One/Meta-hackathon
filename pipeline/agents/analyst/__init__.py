"""The brand analyst: product photos in, a BrandProfile and a 3D product out.

    analyse.py   the whole of it: analyse(run, photo, category), the turntable, the contact sheet
    segment.py   SAM 3.1: the product's mask, then its parts (cap, label)
    palette.py   the colours, k-means in Lab, part by part
    materials.py Muse Spark vision: brand, height, materials, typography, mood, do-nots
    profile.py   the mask's outline as the lathe profile of the 3D shape
    label.py     the label cut from the photo and unrolled
"""

from .analyse import Analysis, analyse, contact_sheet, turntable, turntable_frames, turntable_video

__all__ = ["Analysis", "analyse", "contact_sheet", "turntable", "turntable_frames", "turntable_video"]
