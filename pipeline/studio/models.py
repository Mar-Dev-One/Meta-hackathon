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


def normalize(source: Path | str, out: Path | str, height: float, up: str = "+y", turn: float = 0.0) -> Path:
    """`source` as a product: rotated so `up` ("+y", "+z", "-z", ...) points up
    and turned `turn` degrees about the vertical, centred over the origin,
    standing on y = 0 and scaled to `height` meters; written as a GLB with
    vertex normals."""
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
    baked = trimesh.Scene()
    for mesh in scene.dump(concatenate=False):
        baked.add_geometry(mesh)
    scene = baked
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    scene.export(str(out), file_type="glb", include_normals=True)   # without them the Studio can't light it
    return out


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
    out = normalize(source, out, height, up=up, turn=turn)
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
    top third are the cap (if there's a cap), the rest the body. A texture
    is kept as detail, turned grey and tinted with the part's colour.

    A glass body (its finish has transmission) is dressed as the Studio's
    own glass products are: one glass, tinted with what it holds over its
    width. The Studio shows the scene behind a see-through surface but not
    other see-through surfaces, so a liquid modelled inside a glass shell
    would vanish: the largest piece its modeller made see-through is kept as
    the glass, given the liquid's colour, and the body pieces inside it go."""
    scene = load(source)
    top = scene.bounds[1][1]
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
