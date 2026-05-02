import trimesh
from pathlib import Path
from datetime import datetime


def export_mesh(mesh: trimesh.Trimesh, output_path: str = None) -> str:
    """Export mesh to STL. Returns the path where it was saved."""
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = str(Path.home() / "Desktop" / f"custom_mouse_{ts}.stl")
    mesh.export(output_path)
    return output_path
