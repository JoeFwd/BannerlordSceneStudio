"""Read-only, full-precision diagnostics for scene-file navmeshes.

Unlike query_faces, these queries test polygon footprints, not centroids.
Counts include all matches even when the returned face detail is limited.
No result here asserts native editor visibility or campaign traversability.
"""
from collections import Counter
import hashlib
from pathlib import Path

from blnav import rnm1


def validate_topology(mesh, include_errors=True):
    """Validate native face sizes and report high-degree topology smells.

    Degree is computed from unique, canonical face-boundary edges rather than
    trusting the serialized edge table, which may be stale while the mesh is
    being edited. Shared face edges therefore contribute once at each endpoint.

    A degree above four is only a warning: official Sandbox and NavalDLC maps
    contain thousands of such vertices, commonly where triangles meet. Invalid
    face arity and vertices unused by every face remain errors.
    """
    invalid_faces = [
        {"face_index": face_index, "vertex_count": len(face.vertex_ids)}
        for face_index, face in enumerate(mesh.faces)
        if len(face.vertex_ids) not in (3, 4)
    ]

    referenced_vertices = {
        vertex_id
        for face in mesh.faces
        for vertex_id in face.vertex_ids
        if 0 <= vertex_id < len(mesh.vertices)
    }
    boundary_edges = {
        (min(first, second), max(first, second))
        for face in mesh.faces
        for first, second in zip(
            face.vertex_ids, face.vertex_ids[1:] + face.vertex_ids[:1]
        )
        if 0 <= first < len(mesh.vertices) and 0 <= second < len(mesh.vertices)
    }
    degrees = [0] * len(mesh.vertices)
    for first, second in boundary_edges:
        degrees[first] += 1
        if second != first:
            degrees[second] += 1

    over_connected = [
        {"vertex_id": vertex_id, "degree": degree}
        for vertex_id, degree in enumerate(degrees)
        if degree > 4
    ]
    isolated = [
        {"vertex_id": vertex_id, "degree": degree}
        for vertex_id, degree in enumerate(degrees)
        if degree == 0 or vertex_id not in referenced_vertices
    ]
    result = {
        "passed": not invalid_faces and not isolated,
        "error_count": len(invalid_faces) + len(isolated),
        "warning_count": len(over_connected),
        "invalid_triangle_or_quad_face_count": len(invalid_faces),
        "over_connected_vertex_count": len(over_connected),
        "isolated_vertex_count": len(isolated),
        "degree_definition": "unique canonical face-boundary edges incident to the vertex",
        "maximum_vertex_degree": 4,
    }
    if include_errors:
        result.update({
            "invalid_triangle_or_quad_faces": invalid_faces,
            "high_degree_vertices": over_connected,
            "isolated_vertices": isolated,
        })
    return result


def validate_navmesh(sess, include_errors=True):
    """Validate the current working navmesh and include its file identity."""
    return {
        "identity": mesh_identity(sess),
        **validate_topology(sess.mesh, include_errors=include_errors),
    }


def _contains(points, x, y):
    inside = False
    for a, b in zip(points, points[1:] + points[:1]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        cross = dx * (y - a[1]) - dy * (x - a[0])
        if abs(cross) <= 1e-10 and min(a[0], b[0]) <= x <= max(a[0], b[0]) and min(a[1], b[1]) <= y <= max(a[1], b[1]):
            return True
        if (a[1] > y) != (b[1] > y) and x < a[0] + (y - a[1]) * dx / dy:
            inside = not inside
    return inside


def _clip(points, bounds):
    result = [p[:2] for p in points]
    for axis, value, sign in ((0, bounds[0], 1), (0, bounds[2], -1),
                              (1, bounds[1], 1), (1, bounds[3], -1)):
        clipped = []
        if not result:
            break
        previous = result[-1]
        for current in result:
            previous_in = sign * (previous[axis] - value) >= 0
            current_in = sign * (current[axis] - value) >= 0
            if previous_in != current_in:
                t = (value - previous[axis]) / (current[axis] - previous[axis])
                clipped.append([previous[k] + t * (current[k] - previous[k]) for k in range(2)])
            if current_in:
                clipped.append(current)
            previous = current
        result = clipped
    return result


def _area(points):
    return abs(sum(a[0] * b[1] - b[0] * a[1]
                   for a, b in zip(points, points[1:] + points[:1]))) / 2


def _face(mesh, index):
    face = mesh.faces[index]
    return {"index": index, "vertex_ids": list(face.vertex_ids),
            "edge_ids": list(face.edge_ids),
            "vertices": [list(mesh.vertices[v]) for v in face.vertex_ids],
            **{f"g{k}": getattr(face, f"g{k}") for k in range(1, 7)}}


def mesh_identity(sess):
    working = hashlib.sha256(sess.mesh.serialize()).hexdigest()
    path = Path(sess.navmesh_path)
    disk = path.read_bytes() if path.exists() else None
    disk_payload = hashlib.sha256(rnm1.read(str(path))).hexdigest() if disk is not None else None
    return {"scene_dir": sess.scene_dir, "dirty": sess.dirty,
            "working_payload_sha256": working,
            "disk_container_sha256": hashlib.sha256(disk).hexdigest() if disk is not None else None,
            "disk_payload_sha256": disk_payload,
            "working_matches_disk": working == disk_payload}


def inspect_region(sess, min_x, min_y, max_x, max_y, limit=200):
    if min_x >= max_x or min_y >= max_y or not 0 <= limit <= 1000:
        raise ValueError("Use positive-area bounds and a detail limit from 0 to 1000")
    mesh = sess.mesh
    bounds = (min_x, min_y, max_x, max_y)
    used = {v for face in mesh.faces for v in face.vertex_ids}
    regional_vertices = {i for i, p in enumerate(mesh.vertices)
                         if min_x <= p[0] <= max_x and min_y <= p[1] <= max_y}
    ids, areas = [], Counter()
    for i, face in enumerate(mesh.faces):
        points = [mesh.vertices[v] for v in face.vertex_ids]
        if not points or max(p[0] for p in points) < min_x or min(p[0] for p in points) > max_x or max(p[1] for p in points) < min_y or min(p[1] for p in points) > max_y:
            continue
        area = _area(_clip(points, bounds))
        if area > 0:
            ids.append(i)
            areas[face.g3] += area
    counts = Counter(mesh.faces[i].g3 for i in ids)
    return {"identity": mesh_identity(sess), "bounds": list(bounds),
            "selection": "positive-area polygon intersection; not centroid containment",
            "matching_face_count": len(ids), "face_counts_by_g3": dict(counts),
            "summed_face_area_by_g3": dict(areas),
            "area_note": "Areas sum faces; overlaps are counted repeatedly, not union coverage",
            "vertices_global": {"total": len(mesh.vertices), "referenced": len(used),
                                "unreferenced": len(mesh.vertices) - len(used)},
            "vertices_in_bounds": {"total": len(regional_vertices),
                                   "referenced": len(regional_vertices & used),
                                   "unreferenced": len(regional_vertices - used)},
            "faces": [_face(mesh, i) for i in ids[:limit]],
            "truncated": len(ids) > limit}


def probe_point(sess, x, y):
    mesh = sess.mesh
    ids = [i for i, face in enumerate(mesh.faces)
           if _contains([mesh.vertices[v] for v in face.vertex_ids], x, y)]
    return {"identity": mesh_identity(sess), "point": [x, y],
            "selection": "closed XY polygon footprint, all terrain types",
            "decoded_terrain_height": sess.sample_height(x, y) if sess.heights is not None else None,
            "faces": [_face(mesh, i) for i in ids],
            "warning": "File geometry only; neither native visibility nor navigability is inferred"}
