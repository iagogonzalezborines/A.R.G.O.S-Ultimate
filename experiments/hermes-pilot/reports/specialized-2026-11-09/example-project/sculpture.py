"""Build and render a small blue decorative vase sculpture in Blender 5.2."""
import bpy
import math
import os
from mathutils import Vector


def lathe_mesh(name, profile, segments=96):
    verts, faces = [], []
    # The first and last profile entries are unique axial caps; do not make
    # degenerate rings of coincident vertices at radius zero.
    bottom_z = profile[0][0]
    top_z = profile[-1][0]
    rings = profile[1:-1]
    verts.append((0.0, 0.0, bottom_z))
    for z, radius in rings:
        for i in range(segments):
            a = 2.0 * math.pi * i / segments
            verts.append((radius * math.cos(a), radius * math.sin(a), z))
    top_index = len(verts)
    verts.append((0.0, 0.0, top_z))
    ring_count = len(rings)
    # Bottom fan, oriented toward -Z.
    for i in range(segments):
        faces.append((0, 1 + (i + 1) % segments, 1 + i))
    for row in range(ring_count - 1):
        for i in range(segments):
            a = 1 + row * segments + i
            b = 1 + row * segments + (i + 1) % segments
            faces.append((a, b, b + segments, a + segments))
    # Top fan.
    last_ring = 1 + (ring_count - 1) * segments
    for i in range(segments):
        faces.append((last_ring + i, last_ring + (i + 1) % segments, top_index))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    return mesh


def look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat('-Z', 'Y').to_euler()


def build():
    out_dir = os.path.dirname(os.path.abspath(__file__))
    # Start clean, and construct exactly one mesh object plus camera and light.
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)

    # A closed, thick-walled stylized vessel silhouette, in meters.
    profile = [
        (0.00, 0.43), (0.035, 0.49), (0.10, 0.52), (0.20, 0.56),
        (0.38, 0.61), (0.62, 0.62), (0.83, 0.56), (1.02, 0.44),
        (1.18, 0.33), (1.34, 0.28), (1.52, 0.29), (1.68, 0.35),
        (1.76, 0.37), (1.80, 0.34), (1.80, 0.25), (1.74, 0.24),
        (1.62, 0.235), (1.49, 0.23), (1.36, 0.24), (1.20, 0.28),
        (1.04, 0.37), (0.84, 0.49), (0.62, 0.54), (0.40, 0.53),
        (0.23, 0.47), (0.16, 0.0),
    ]
    # Profile winds around the interior and ends on its bottom center. The
    # slightly recessed interior floor gives the mouth a visible dark depth.
    mesh = lathe_mesh('Azure Vessel Mesh', profile)
    vessel = bpy.data.objects.new('Azure Vessel', mesh)
    bpy.context.collection.objects.link(vessel)
    for poly in mesh.polygons:
        poly.use_smooth = len(poly.vertices) == 4

    # Subtle polished cobalt ceramic.
    mat = bpy.data.materials.new('Deep Azure Glaze')
    mat.diffuse_color = (0.018, 0.16, 0.62, 1.0)
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    bsdf.inputs['Base Color'].default_value = (0.008, 0.095, 0.48, 1.0)
    bsdf.inputs['Metallic'].default_value = 0.04
    bsdf.inputs['Roughness'].default_value = 0.42
    vessel.data.materials.append(mat)

    # Camera and broad area source; no ground plane means the mesh count stays one.
    camera_data = bpy.data.cameras.new('Camera')
    camera = bpy.data.objects.new('Camera', camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = (3.65, -5.8, 2.72)
    look_at(camera, (0.0, 0.0, 0.91))
    camera_data.type = 'ORTHO'
    camera_data.ortho_scale = 2.75
    camera_data.lens = 52
    bpy.context.scene.camera = camera

    light_data = bpy.data.lights.new('Key Softbox', 'AREA')
    light = bpy.data.objects.new('Key Softbox', light_data)
    bpy.context.collection.objects.link(light)
    light.location = (-3.2, -4.0, 4.7)
    look_at(light, (0.0, 0.0, 0.85))
    light_data.energy = 700
    light_data.shape = 'DISK'
    light_data.size = 3.2

    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 4
    scene.cycles.use_denoising = False
    scene.render.resolution_x = 320
    scene.render.resolution_y = 240
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.film_transparent = False
    scene.world.color = (0.045, 0.045, 0.045)
    scene.view_settings.view_transform = 'AgX'
    scene.render.filepath = os.path.join(out_dir, 'preview.png')
    scene.camera.data.lens = 52
    # Set a dark slate world background via nodes for a clean product portrait.
    scene.world.use_nodes = True
    bg = next(n for n in scene.world.node_tree.nodes if n.type == 'BACKGROUND')
    bg.inputs['Color'].default_value = (0.018, 0.026, 0.052, 1.0)
    bg.inputs['Strength'].default_value = 0.34

    # Save editable scene, export only the single sculpture mesh, and render preview.
    blend_path = os.path.join(out_dir, 'sculpture.blend')
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    bpy.ops.export_scene.gltf(filepath=os.path.join(out_dir, 'sculpture.glb'), export_format='GLB', use_selection=False)
    bpy.ops.render.render(write_still=True)
    return {'blend': blend_path, 'mesh_objects': sum(o.type == 'MESH' for o in scene.objects),
            'camera': camera.name, 'light': light.name, 'engine': scene.render.engine,
            'device': scene.cycles.device, 'samples': scene.cycles.samples,
            'resolution': [scene.render.resolution_x, scene.render.resolution_y]}


if __name__ == '__main__':
    print('SCULPTURE_RESULT', build())
