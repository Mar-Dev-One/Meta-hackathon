"""Small storyboards and models for the tests: no Studio, network or Spark."""

import trimesh

from pipeline.schemas import CameraMove, Lighting, Look, Product, Shot, Storyboard


def storyboard(durations=(3.0, 3.0, 3.5), moves=None, **look) -> Storyboard:
    """A perfume ad (the template product) with shots of `durations`, the
    last the hero; `look` fields override the plain set's."""
    moves = moves or ["orbit", "dolly", "static", "crane", "truck", "static"]
    shots = [Shot(id=f"s{i + 1}", intent="-", duration=d,
                  camera=CameraMove(move=moves[i % len(moves)], azimuth=20.0 * i))
             for i, d in enumerate(durations)]
    return Storyboard(title="test", brief="-", style="test", look=Look(lighting=Lighting(preset="three_point"), **look),
                      product=Product(template="perfume"), shots=shots)


def box(size, at, colour=None) -> trimesh.Trimesh:
    """A box `size` (x, y, z meters) with its centre at `at`, of a flat `colour` (RGBA 0..255) if given."""
    mesh = trimesh.creation.box(size)
    mesh.apply_translation(at)
    if colour is not None:
        mesh.visual = trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(baseColorFactor=colour))
    return mesh
