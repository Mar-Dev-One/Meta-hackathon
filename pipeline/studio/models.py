"""Products as 3D model files: any shape, not only round ones (a model found
online, or one you have).

    fit("raw.glb", "product.glb", height=0.15, aspect=2.1, parts={"body": {...}, "cap": {...}})
    normalize("raw.glb", "product.glb", height=0.15)    # upright, centred, standing on y = 0, 15 cm tall
    height, width = size("product.glb")
    key = install(studio, "product.glb")                # "products/model_<hash>.glb", for place_model

A product's model is kept in the Studio's units and pose: meters, Y up, its
front towards +Z, its base centre at the origin. Then it's placed like the
spun products: its base on the pedestal, at the origin.

fit() makes a downloaded model the brand's product: stood the way it's
told (pipeline.agents.stager: Muse Spark, looking at the photo), or else
the way up whose proportions match the product in its photo (models often
lie on their side or back), scaled, and dressed in the brand's finish part
by part (the top piece is the cap; glass becomes real glass holding the
product's liquid).
"""

import hashlib
import json
import shutil
import struct
from pathlib import Path

import numpy as np
import trimesh
from PIL import ImageOps

UPS = ("+y", "+z", "-z", "+x", "-x", "-y")   # the ways a model can stand, the usual (glTF's Y up) first
KEEP_Y = 0.15     # +y wins unless another way's proportions match the photo this much better (log ratio)
CAP_FROM = 0.65   # a piece centred above this share of the height is the cap (collar, stopper, lid)
SEE_THROUGH = 250 # a piece whose colour's alpha is under this (of 255) was made see-through: glass


def load(path: Path | str) -> trimesh.Scene:
    return trimesh.load(str(path), force="scene")


def size(path: Path | str) -> tuple[float, float]:
    """The model's height (Y) and widest horizontal size (X or Z), in meters."""
    lo, hi = load(path).bounds
    return float(hi[1] - lo[1]), float(max(hi[0] - lo[0], hi[2] - lo[2]))


def footprint(path: Path | str) -> tuple[float, float, float]:
    """The model seen from above, along its own axes (however it's turned):
    its length along its longest horizontal axis, its thickness across it,
    in meters, and the azimuth (degrees, the Studio's: 0 the front, 90 its
    right) a camera looking along that axis stands at, where it's edge-on."""
    points = np.concatenate([m.vertices[:, [0, 2]] for m in load(path).dump(concatenate=False)])
    centred = points - points.mean(axis=0)
    _, vectors = np.linalg.eigh(np.cov(centred.T))
    long_axis = vectors[:, -1]                      # the direction it's longest in (x, z)
    along, across = centred @ long_axis, centred @ vectors[:, 0]
    azimuth = float(np.degrees(np.arctan2(long_axis[0], long_axis[1]))) % 180
    return float(np.ptp(along)), float(np.ptp(across)), azimuth


def normalize(source: Path | str, out: Path | str, height: float, up: str = "+y", turn: float = 0.0,
              strip: bool = False) -> Path:
    """`source` as a product: rotated so `up` ("+y", "+z", "-z", ...) points up
    and turned `turn` degrees about the vertical, centred over the origin,
    standing on y = 0 and scaled to `height` meters; written as a GLB with
    vertex normals. With `strip`, a base it came standing on (a coaster, a
    stand, a floor: strip_base) is taken off first."""
    scene = load(source)
    axis = {"x": 0, "y": 1, "z": 2}[up[1]]
    sign = -1.0 if up[0] == "-" else 1.0
    if axis != 1 or sign < 0:
        direction = np.zeros(3)
        direction[axis] = sign
        scene.apply_transform(_rotation_between(direction, np.array([0.0, 1.0, 0.0])))
    if turn:
        scene.apply_transform(trimesh.transformations.rotation_matrix(np.radians(turn), [0, 1, 0]))
    lo, hi = scene.bounds
    scene.apply_translation([-(lo[0] + hi[0]) / 2, -lo[1], -(lo[2] + hi[2]) / 2])
    scene.apply_scale(height / max(hi[1] - lo[1], 1e-9))
    # Into the vertices themselves: trimesh keeps the moves above on the scene's nodes, and a glass's
    # thickness (KHR_materials_volume) is in its mesh's own units, so a mesh left in its file's units
    # (often hundreds of times too big) gets almost no thickness: no tint, no refraction.
    meshes = scene.dump(concatenate=False)
    if strip and strip_base(meshes):   # the product alone: stood on y = 0 and scaled to `height` again
        meshes = [m for m in meshes if len(m.faces)]
        lo, hi = trimesh.Scene(meshes).bounds
        for m in meshes:
            m.apply_translation([-(lo[0] + hi[0]) / 2, -lo[1], -(lo[2] + hi[2]) / 2])
            m.apply_scale(height / max(hi[1] - lo[1], 1e-9))
    baked = trimesh.Scene()
    for mesh in meshes:
        baked.add_geometry(mesh)
    scene = baked
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    scene.export(str(out), file_type="glb", include_normals=True)   # without them the Studio can't light it
    return out


def faces(path: Path | str) -> int:
    """The model's faces, every placed copy of a mesh counted."""
    scene = load(path)
    return sum(len(scene.geometry[name].faces) for node in scene.graph.nodes_geometry
               for name in [scene.graph[node][1]])


BASE_THIN = 0.05   # of the model's height: a slab under it at most this thick is a base, not the product
BASE_WIDE = 0.5    # of the product's narrower width: a base is at least this wide (a coaster, a stand; not feet)
BASE_SOLID = 0.005 # of the height: a base this thick at least, or wider than the product (a floor); a flat
                   # disc within its outline is its own bottom


def _parts(mesh: trimesh.Trimesh) -> np.ndarray:
    """Each face's connected part (faces sharing vertices, seams joined), as labels."""
    joined = trimesh.Trimesh(mesh.vertices.copy(), mesh.faces.copy(), process=False)
    joined.merge_vertices(merge_tex=True, merge_norm=True)
    return trimesh.graph.connected_component_labels(joined.face_adjacency, node_count=len(joined.faces))


def strip_base(meshes: list[trimesh.Trimesh]) -> int:
    """Takes off (in place) what a model came standing on: the parts at its
    very bottom, at most BASE_THIN of its height thick (and at least
    BASE_SOLID, unless wider than the rest), at least BASE_WIDE of the
    rest's narrower width across, with the rest standing on top of them (a coaster, a display stand, a patch of floor). Returns the faces
    taken off: 0 when there's no such base. A flat disc within the
    product's outline is its own bottom, and stays."""
    lo, hi = trimesh.Scene(meshes).bounds
    tall = hi[1] - lo[1]
    parts = []   # (mesh, its faces' mask, lowest point, highest point)
    for mesh in meshes:
        if not len(mesh.faces):
            continue
        labels = _parts(mesh)
        for k in range(labels.max() + 1):
            mask = labels == k
            points = mesh.vertices[np.unique(mesh.faces[mask])]
            parts.append((mesh, mask, points.min(0), points.max(0)))
    base = [p for p in parts if p[3][1] - lo[1] <= BASE_THIN * tall]
    rest = [p for p in parts if p[3][1] - lo[1] > BASE_THIN * tall]
    if not base or not rest:
        return 0
    top = max(p[3][1] for p in base)
    rest_lo = np.min([p[2] for p in rest], axis=0)
    rest_hi = np.max([p[3] for p in rest], axis=0)
    base_lo = np.min([p[2] for p in base], axis=0)
    base_hi = np.max([p[3] for p in base], axis=0)
    stands_on = rest_lo[1] >= top - 0.01 * tall
    across, rest_across = base_hi[[0, 2]] - base_lo[[0, 2]], rest_hi[[0, 2]] - rest_lo[[0, 2]]
    wide = min(across) >= BASE_WIDE * min(rest_across)
    a_thing = top - base_lo[1] >= BASE_SOLID * tall or max(across) > max(rest_across)
    if not (stands_on and wide and a_thing):
        return 0
    gone: dict[int, tuple] = {}   # one mesh's base pieces together: its masks are of its faces before any go
    for mesh, mask, _, _ in base:
        _, before = gone.get(id(mesh), (mesh, np.zeros_like(mask)))
        gone[id(mesh)] = (mesh, before | mask)
    for mesh, mask in gone.values():
        mesh.update_faces(~mask)
        mesh.remove_unreferenced_vertices()
    return sum(int(mask.sum()) for _, mask in gone.values())


def _rotation_between(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """The 4x4 rotation taking unit vector `a` to `b`."""
    v, c = np.cross(a, b), float(np.dot(a, b))
    if np.linalg.norm(v) < 1e-9:   # parallel: none, or half a turn about any perpendicular axis
        return np.eye(4) if c > 0 else trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0])
    return trimesh.transformations.rotation_matrix(np.arccos(np.clip(c, -1, 1)), v)


def orient(source: Path | str, aspect: float) -> tuple[str, float]:
    """(up, turn) that stand the model the way its proportions best match a
    front view `aspect` tall (height / width, the product's outline in its
    photo): the up axis, and 0 or 90 degrees so its matching side faces the
    camera. Upside down can't be told from upright this way, so "+" wins."""
    scene = load(source)
    extents = scene.bounds[1] - scene.bounds[0]
    target = np.log(max(aspect, 1e-3))
    best, usual = None, None
    for up in UPS:
        axis = {"x": 0, "y": 1, "z": 2}[up[1]]
        height = extents[axis]
        across = [extents[i] for i in range(3) if i != axis]   # the two horizontal sizes, in x, z order
        for turn, width in ((0.0, across[0]), (90.0, across[1])):
            error = abs(np.log(max(height, 1e-9) / max(width, 1e-9)) - target)
            if up == "+y" and (usual is None or error < usual[0]):
                usual = (error, up, turn)
            if best is None or error < best[0]:
                best = (error, up, turn)
    return (usual[1], usual[2]) if usual[0] - best[0] < KEEP_Y else (best[1], best[2])


def fit(source: Path | str, out: Path | str, height: float, aspect: float | None = None,
        parts: dict[str, dict] | None = None, up: str | None = None, turn: float = 0.0) -> Path:
    """A downloaded model as the brand's product: stood `up` and turned
    `turn` degrees if given, else oriented to match the photo's `aspect` (if
    given), normalized to `height`, and dressed in `parts` ({"body": finish,
    "cap": finish}, Surface fields: colour, metallic, roughness, transmission,
    attenuation, clear coat) if given."""
    if not up:
        up, turn = orient(source, aspect) if aspect else ("+y", 0.0)
    out = normalize(source, out, height, up=up, turn=turn, strip=True)
    if parts:
        dress(out, out, parts)
    if not (parts and any(p.get("transmission") for p in parts.values())):
        opaque(out)   # not glass: solid, whatever its modeller set
    return out


def _linear(hex_colour: str) -> list[float]:
    c = np.array([int(hex_colour[i:i + 2], 16) for i in (1, 3, 5)]) / 255.0
    return list(np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4))


def _pieces(scene: trimesh.Scene) -> list[dict]:
    """Each placed mesh with its bounds in the scene, and whether its own
    material was see-through (a modeller's glass)."""
    out = []
    for node in scene.graph.nodes_geometry:
        transform, name = scene.graph[node]
        mesh = scene.geometry[name]
        points = trimesh.transform_points(mesh.vertices, transform)
        material = getattr(mesh.visual, "material", None)
        factor = getattr(material, "baseColorFactor", None)
        alpha = int(factor[3]) if factor is not None and len(factor) > 3 else 255
        out.append({"name": name, "mesh": mesh, "lo": points.min(0), "hi": points.max(0),
                    "see_through": alpha < SEE_THROUGH or getattr(material, "alphaMode", None) == "BLEND"})
    return out


def _inside(a: dict, b: dict, margin: float = 0.02) -> bool:
    """Whether piece a's box lies within piece b's (with a little give)."""
    size = b["hi"] - b["lo"]
    return bool(np.all(a["lo"] >= b["lo"] - margin * size) and np.all(a["hi"] <= b["hi"] + margin * size))


def dress(source: Path | str, out: Path | str, parts: dict[str, dict]) -> Path:
    """Each piece of the model in its part's finish. Pieces centred in the
    top third are the cap (if there's a cap; a mesh with pieces on both
    sides split first, split_caps), the rest the body. A texture
    is kept as detail, turned grey and tinted with the part's colour.

    A glass body (its finish has transmission) is dressed as the Studio's
    own glass products are: one glass, tinted with what it holds over its
    width. The Studio shows the scene behind a see-through surface but not
    other see-through surfaces, so a liquid modelled inside a glass shell
    would vanish: the largest piece its modeller made see-through is kept as
    the glass, given the liquid's colour, and the body pieces inside it go."""
    scene = load(source)
    top = scene.bounds[1][1]
    if "cap" in parts:
        split_caps(scene, CAP_FROM * top)
    pieces = _pieces(scene)
    body = parts.get("body") or next(iter(parts.values()))
    for p in pieces:
        p["part"] = "cap" if "cap" in parts and (p["lo"][1] + p["hi"][1]) / 2 >= CAP_FROM * top else "body"
        p["finish"] = parts["cap"] if p["part"] == "cap" else body

    if body.get("transmission"):
        for p in pieces:   # glass is as thick as it's wide, like a spun glass part (Products.c)
            if p["part"] == "body":
                p["finish"] = body | {"thickness": float(max(p["hi"][0] - p["lo"][0], p["hi"][2] - p["lo"][2]))}
        glass = [p for p in pieces if p["part"] == "body" and p["see_through"]]
        shell = max(glass, key=lambda p: float(np.prod(p["hi"] - p["lo"])), default=None)
        if shell:
            held = [p for p in pieces if p["part"] == "body" and p is not shell and _inside(p, shell)]
            for p in held:
                scene.delete_geometry(p["name"])
            pieces = [p for p in pieces if p not in held]
            shell["part"] = "glass"

    names = {}
    for i, p in enumerate(pieces):
        material = _dressed(p["mesh"], p["finish"], f"{p['part']}_{i}")
        p["mesh"].visual = trimesh.visual.TextureVisuals(uv=getattr(p["mesh"].visual, "uv", None), material=material)
        names[material.name] = p["finish"]
    scene.export(str(out), file_type="glb", include_normals=True)
    _add_extensions(Path(out), names)
    return Path(out)


def split_caps(scene: trimesh.Scene, cap_from: float) -> int:
    """Splits (in place) each mesh holding both a cap and some of the body
    in two: its connected pieces centred above `cap_from` (a height in the
    scene) apart from the rest. A modeller often makes a bottle and its
    stopper one mesh (NOCTIS's), which, centred low, was dressed all as the
    body: a gold cap came out smoked glass. Returns the meshes split; a mesh
    placed more than once is left whole."""
    nodes: dict[str, list] = {}
    for node in scene.graph.nodes_geometry:
        transform, name = scene.graph[node]
        nodes.setdefault(name, []).append(transform)
    split = 0
    for name, transforms in nodes.items():
        mesh = scene.geometry[name]
        if len(transforms) > 1 or not len(mesh.faces):
            continue
        labels = _parts(mesh)
        if labels.max() == 0:
            continue
        heights = trimesh.transform_points(mesh.vertices, transforms[0])[:, 1]
        cap = np.zeros(len(mesh.faces), bool)
        for k in range(labels.max() + 1):
            mask = labels == k
            ys = heights[np.unique(mesh.faces[mask])]
            cap[mask] = (ys.min() + ys.max()) / 2 >= cap_from
        if cap.all() or not cap.any():
            continue
        halves = {"cap": mesh.submesh([np.flatnonzero(cap)], append=True),
                  "body": mesh.submesh([np.flatnonzero(~cap)], append=True)}
        scene.delete_geometry(name)
        for part, half in halves.items():
            scene.add_geometry(half, geom_name=f"{name}_{part}", transform=transforms[0])
        split += 1
    return split


def _dressed(mesh: trimesh.Trimesh, finish: dict, name: str) -> trimesh.visual.material.PBRMaterial:
    """A new material for `mesh` in `finish`: its texture greyed as detail
    under the finish's colour (none for glass)."""
    texture = None
    old = getattr(mesh.visual, "material", None)
    if old is not None and not finish.get("transmission"):
        image = getattr(old, "baseColorTexture", None) or getattr(old, "image", None)
        if image is not None:
            grey = ImageOps.grayscale(image.convert("RGB"))
            mean = max(np.asarray(grey).mean(), 1.0)
            texture = grey.point(lambda v: min(255, int(v * 200 / mean))).convert("RGB")   # detail around a bright mean
    colour = _linear(finish.get("color") or "#FFFFFF") + [1.0]
    return trimesh.visual.material.PBRMaterial(name=name, baseColorFactor=colour, baseColorTexture=texture,
                                               metallicFactor=float(finish.get("metallic", 0.0)),
                                               roughnessFactor=float(finish.get("roughness", 0.5)),
                                               doubleSided=bool(finish.get("transmission")))


def _add_extensions(glb: Path, finishes: dict[str, dict]) -> None:
    """Glass and clear coat into the GLB's materials, as the glTF extensions
    the Studio reads (KHR_materials_transmission, _volume, _ior, _clearcoat)."""
    gltf, rest = _read_glb(glb)
    used = set(gltf.get("extensionsUsed", []))
    for material in gltf.get("materials", []):
        finish = finishes.get(material.get("name"), {})
        ext = {}
        if finish.get("transmission"):
            ext["KHR_materials_transmission"] = {"transmissionFactor": float(finish["transmission"])}
            ext["KHR_materials_ior"] = {"ior": float(finish.get("ior") or 1.5)}
            volume = {"thicknessFactor": float(finish.get("thickness") or 0.05)}
            if finish.get("attenuation_color") and finish.get("attenuation_distance"):
                volume.update(attenuationColor=_linear(finish["attenuation_color"]),
                              attenuationDistance=float(finish["attenuation_distance"]))
            ext["KHR_materials_volume"] = volume
        if finish.get("clearcoat"):
            ext["KHR_materials_clearcoat"] = {"clearcoatFactor": float(finish["clearcoat"]),
                                              "clearcoatRoughnessFactor": float(finish.get("clearcoat_roughness") or 0.05)}
        if ext:
            material.setdefault("extensions", {}).update(ext)
            used.update(ext)
    if used:
        gltf["extensionsUsed"] = sorted(used)
    _write_glb(glb, gltf, rest)


def opaque(glb: Path | str) -> Path:
    """Every material of the model solid: a modeller's "blend" (see-through,
    for lace or mesh detail) makes a whole shoe a ghost in the Studio. For
    a product that isn't glass."""
    glb = Path(glb)
    gltf, rest = _read_glb(glb)
    for material in gltf.get("materials", []):
        material["alphaMode"] = "OPAQUE"
        material.pop("alphaCutoff", None)
        factor = material.get("pbrMetallicRoughness", {}).get("baseColorFactor")
        if factor and len(factor) == 4:
            factor[3] = 1.0
    _write_glb(glb, gltf, rest)
    return glb


def finish_unset(glb: Path | str, metallic: float, roughness: float) -> list[str]:
    """The finish read from the photo (`metallic`, `roughness`) on the
    model's materials that have none of their own: no metallic-roughness
    texture and glTF's defaults (metallic 1, roughness 1), which render
    plastic or ceramic as dull grey metal. A modeller's finish (a texture, or
    values set) is kept: a watch's steel, leather and glass stay as made.
    Returns the materials given the finish, by name."""
    glb = Path(glb)
    gltf, rest = _read_glb(glb)
    given = []
    for i, material in enumerate(gltf.get("materials", [])):
        pbr = material.setdefault("pbrMetallicRoughness", {})
        if "metallicRoughnessTexture" in pbr or pbr.get("metallicFactor", 1.0) != 1.0 or pbr.get("roughnessFactor", 1.0) != 1.0:
            continue
        pbr["metallicFactor"], pbr["roughnessFactor"] = float(metallic), float(roughness)
        given.append(material.get("name") or f"material {i}")
    if given:
        _write_glb(glb, gltf, rest)
    return given


DECAL_GRID = 24        # a decal's vertices across and down: enough to follow a curved front
DECAL_LIFT = 0.0006    # meters it stands off the surface, so it doesn't flicker into it (as a spun label's)


def _front(triangles: np.ndarray, points: np.ndarray) -> np.ndarray:
    """For each (x, y) point, the frontmost z (largest: the front is +Z) of
    the surface over it, NaN where it isn't over the model."""
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    lo, hi = triangles[:, :, :2].min(axis=1), triangles[:, :, :2].max(axis=1)
    d = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    usable = np.abs(d) > 1e-12   # seen edge-on from the front: no area to stand on
    out = np.full(len(points), np.nan)
    for i, (x, y) in enumerate(points):
        near = usable & (lo[:, 0] <= x) & (x <= hi[:, 0]) & (lo[:, 1] <= y) & (y <= hi[:, 1])
        if not near.any():
            continue
        ta, tb, tc, td = a[near], b[near], c[near], d[near]
        u = ((tb[:, 1] - tc[:, 1]) * (x - tc[:, 0]) + (tc[:, 0] - tb[:, 0]) * (y - tc[:, 1])) / td
        v = ((tc[:, 1] - ta[:, 1]) * (x - tc[:, 0]) + (ta[:, 0] - tc[:, 0]) * (y - tc[:, 1])) / td
        w = 1 - u - v
        inside = (u >= -1e-9) & (v >= -1e-9) & (w >= -1e-9)
        if inside.any():
            out[i] = (u * ta[:, 2] + v * tb[:, 2] + w * tc[:, 2])[inside].max()
    return out


def add_decal(glb: Path | str, image: Path | str, box: tuple[float, float, float, float]) -> bool:
    """The label laid on the model's front (+Z), in place: a grid over `box`
    (left, top, right, bottom, as shares of the model's front, as the photo
    shows it: top 0), each point moved onto the surface in front of it,
    DECAL_LIFT off it, textured with `image` and blended, so on glass it's
    drawn after the glass and isn't refracted into a ghost. A label is
    wrapped only round a spun shape: a 3D model's product went without
    (Maison Héritage's perfume). The materials' glTF extensions (glass,
    clear coat), which trimesh doesn't keep, are put back by name. False if
    the box isn't over the model."""
    glb = Path(glb)
    before, _ = _read_glb(glb)
    extensions = {m.get("name"): m["extensions"] for m in before.get("materials", []) if m.get("extensions")}
    scene = load(glb)
    (x0, y0, _), (x1, y1, _) = scene.bounds
    left, top, right, bottom = box
    xs = x0 + np.linspace(left, right, DECAL_GRID) * (x1 - x0)
    ys = y1 - np.linspace(top, bottom, DECAL_GRID) * (y1 - y0)   # the photo's top is the model's top
    grid = np.array([(x, y) for y in ys for x in xs])
    triangles = np.concatenate([m.triangles for m in scene.dump(concatenate=False) if len(m.faces)])
    z = _front(triangles, grid)
    if np.isnan(z).all():
        return False
    z = np.where(np.isnan(z), np.nanmax(z), z)   # past the edge of a curved front: level with its furthest point
    vertices = np.column_stack([grid, z + DECAL_LIFT])
    n = DECAL_GRID
    faces = [(r * n + c, (r + 1) * n + c, r * n + c + 1) for r in range(n - 1) for c in range(n - 1)] + \
            [(r * n + c + 1, (r + 1) * n + c, (r + 1) * n + c + 1) for r in range(n - 1) for c in range(n - 1)]
    uv = np.array([(c / (n - 1), 1 - r / (n - 1)) for r in range(n) for c in range(n)])   # glTF's v from the bottom
    from PIL import Image
    material = trimesh.visual.material.PBRMaterial(name="decal", baseColorTexture=Image.open(image).convert("RGBA"),
                                                   metallicFactor=0.0, roughnessFactor=0.55, alphaMode="BLEND")
    mesh = trimesh.Trimesh(vertices, np.array(faces), process=False)   # wound to face +Z, the camera
    if mesh.face_normals[:, 2].mean() < 0:   # a front curving the other way: still facing the camera
        mesh.invert()
    mesh.visual = trimesh.visual.TextureVisuals(uv=uv, material=material)
    scene.add_geometry(mesh, geom_name="decal")
    scene.export(str(glb), file_type="glb", include_normals=True)
    after, rest = _read_glb(glb)
    used = set(after.get("extensionsUsed", []))
    for m in after.get("materials", []):
        if m.get("name") in extensions:
            m.setdefault("extensions", {}).update(extensions[m["name"]])
            used.update(extensions[m["name"]])
    if used:
        after["extensionsUsed"] = sorted(used)
    _write_glb(glb, after, rest)
    return True


def _read_glb(glb: Path) -> tuple[dict, bytes]:
    """A GLB's JSON (its scene, materials ...) and the binary that follows."""
    data = glb.read_bytes()
    length = struct.unpack_from("<I", data, 12)[0]
    return json.loads(data[20:20 + length]), data[20 + length:]


def _write_glb(glb: Path, gltf: dict, rest: bytes) -> None:
    text = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    text += b" " * (-len(text) % 4)
    body = struct.pack("<II", len(text), 0x4E4F534A) + text + rest
    glb.write_bytes(struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body)


def install(studio, path: Path | str) -> str:
    """Copies the model into the Studio's assets (products/, next to the
    spun products) under a name from its content, so the same model is one
    file however often it's placed. Returns its asset key for place_model."""
    key, target = _installed(studio, path)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    return key


def uninstall(studio, path: Path | str) -> None:
    """Removes the model's copy from the Studio's assets (one placed only
    for a moment: the stager's views)."""
    _installed(studio, path)[1].unlink(missing_ok=True)


def _installed(studio, path: Path | str) -> tuple[str, Path]:
    """The model's asset key and where its copy lives in the Studio's assets."""
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    key = f"products/model_{digest}{path.suffix.lower()}"
    return key, Path(studio.exe).parent / "assets" / key
