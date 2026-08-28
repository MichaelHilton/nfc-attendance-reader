"""Phase 6 — smoke + dimensional regression for case/case_gen.py.

Gated on the geometry stack (trimesh / manifold3d / shapely / matplotlib):
`pip install -r case/requirements.txt`. Skips cleanly otherwise. The full
regeneration is slow (~15 s), so it carries the `slow` marker too.
"""
import pathlib
import subprocess
import sys

import pytest

trimesh = pytest.importorskip("trimesh")
pytest.importorskip("manifold3d")
pytest.importorskip("shapely")
pytest.importorskip("matplotlib")

pytestmark = pytest.mark.needs_trimesh

CASE_DIR = pathlib.Path(__file__).resolve().parents[1] / "case"
CASE_GEN = CASE_DIR / "case_gen.py"
STLS = ("case_body.stl", "case_lid.stl", "case_stand.stl")

# Baseline bounding boxes (mm), from a known-good run. Tolerance is generous:
# it catches a broken boolean / wrong dimension, not sub-mm library drift.
BASELINE_EXTENTS = {
    "case_body.stl": (108.1, 118.5, 24.8),
    "case_lid.stl": (102.3, 113.1, 19.8),
    "case_stand.stl": (120.1, 58.8, 71.4),
}
TOL_MM = 1.0


def test_committed_stls_load_and_are_watertight():
    """The STLs checked into case/ are valid, printable solids."""
    for name in STLS:
        mesh = trimesh.load(CASE_DIR / name)
        assert mesh.is_watertight, f"{name} is not watertight"
        assert mesh.volume > 0


@pytest.mark.slow
def test_case_gen_regenerates_consistent_geometry(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(CASE_GEN)],
        cwd=tmp_path, capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, proc.stderr

    for name, baseline in BASELINE_EXTENTS.items():
        stl = tmp_path / name
        assert stl.is_file() and stl.stat().st_size > 0, f"{name} not produced"
        mesh = trimesh.load(stl)
        assert mesh.is_watertight, f"regenerated {name} is not watertight"
        for axis, (got, want) in enumerate(zip(mesh.extents, baseline)):
            assert abs(got - want) < TOL_MM, (
                f"{name} axis {axis}: {got:.2f} mm vs baseline {want} mm "
                f"(> {TOL_MM} mm drift — geometry changed?)"
            )

    # the script self-reports watertightness for each part
    assert proc.stdout.count("watertight=True") == 3, proc.stdout
