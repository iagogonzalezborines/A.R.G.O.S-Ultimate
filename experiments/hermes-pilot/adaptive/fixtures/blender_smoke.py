import bpy,sys,json
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
bpy.ops.mesh.primitive_uv_sphere_add(segments=24,ring_count=12,radius=1)
obj=bpy.context.object;obj.name='DecorativeSphere'
mat=bpy.data.materials.new('ARGOS Blue');mat.diffuse_color=(0.03,0.25,0.8,1);obj.data.materials.append(mat)
bpy.ops.wm.save_as_mainfile(filepath='/workspace/scene.blend')
bpy.ops.export_scene.gltf(filepath='/workspace/scene.glb',export_format='GLB')
bpy.ops.object.camera_add(location=(4,-6,4));camera=bpy.context.object
from mathutils import Vector
camera.rotation_euler=(Vector((0,0,0))-camera.location).to_track_quat('-Z','Y').to_euler();bpy.context.scene.camera=camera
bpy.ops.object.light_add(type='AREA',location=(2,-3,5));bpy.context.object.data.energy=700
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=4;scene.render.resolution_x=320;scene.render.resolution_y=240;scene.render.resolution_percentage=100;scene.render.filepath='/workspace/preview.png'
bpy.ops.render.render(write_still=True)
print('BLENDER_ARTIFACTS_OK')
