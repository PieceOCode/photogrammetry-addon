bl_info = { 
    "name": "Photogrammetry Workflow",
    "author": "Marten Ben Leckebusch",
    "description": """A simple addon, which simplifies common cleanup operations
        that are useful for Photogrammetry objects. Operations include easy
        cropping with cube boundaries, orientating the object by selected normals,
        decimate to low poly and a automated baking of diffuse maps""",
    "blender": (2, 80, 0),
    "location": "View3D", 
    "category": "Generic"
}

# Because Blender has problems with multifile addons all code is in here, sorry :\
import bpy
from mathutils import Vector
from math import sqrt
import math


class CubeCutOperator(bpy.types.Operator):
    """First Call spawns a cube that acts as bounds to the scene. Second call cuts all geometry outside the cube from the active object. Select bounds first, object second."""
    bl_idname = "object.cube_cut"
    bl_label = "Cube Cut Operator"

    first_call = bpy.props.BoolProperty()

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        
        if self.first_call:
            # Instantiate Bounds cube
            bpy.ops.mesh.primitive_cube_add()
            cube = bpy.context.active_object
            cube.display_type = "BOUNDS"
        else:   
            # Activate boolean modifier
            if len(context.selected_objects) != 2: 
                return {'CANCELLED'}
            
            cube = context.selected_objects[0]
            highPoly = context.active_object
            if cube == highPoly: 
                cube = context.selected_objects[1]
            
            boolMod = highPoly.modifiers.new('BoolCut', type='BOOLEAN')
            boolMod.operation = 'INTERSECT'
            boolMod.solver = 'FAST'
            boolMod.object = cube  
            
            bpy.ops.object.modifier_apply(modifier="BoolCut")
            
            # Delete the bounds cube object
            bpy.ops.object.select_all(action='DESELECT')
            cube.select_set(True)
            #bpy.context.view_layer.objects.active = cube
            bpy.ops.object.delete(use_global=False)
        return {'FINISHED'}


class CustomBakeOperator(bpy.types.Operator):
    """Bakes a albedo texture from high to low poly in a single step. Deletes materials in low poly."""
    bl_idname = "object.custom_bake"
    bl_label = "Custom Bake Operator"

    @classmethod
    def poll(cls, context):
        if not context.active_object: 
            return False
        if len(context.selected_objects) != 2: 
            return False
        return True
        
    def execute(self, context):
        highPoly = context.selected_objects[0]
        lowPoly = context.selected_objects[1]
        name = highPoly.name

        # Remove old materials from the LowPoly Object
        for i in range(len(lowPoly.material_slots)):
            bpy.ops.object.material_slot_remove()
        print("Removed old materials on LowPoly.")

        # Create new material, enable nodes and add to LowPoly object
        # mat = bpy.data.materials.new(name + "_LowPoly_Material")  
        mat = bpy.data.materials.new(name + "_LowPoly_Material")
        mat.use_nodes = True;
        lowPoly.data.materials.append(mat)
        print("Added new material.")


        # Create a new image texture to bake to
        img = bpy.data.images.new(
            name= name + "_LowPoly", 
            width = 2048, 
            height = 2048,  
            alpha = False, 
            float_buffer = False, 
            stereo3d = False, 
            is_data = False,
            tiled = False
        )
        print("Created new image node.")

        # Create a new image texture node in the BSDF and assign img
        # Maybe order the whole tree in some kind (set a position for all nodes)
        imgTex = mat.node_tree.nodes.new(type="ShaderNodeTexImage")
        imgTex.image = img

        # Selects the given node in a material
        def selectNode(mat, node):
            for n in mat.node_tree.nodes:
                n.select = False
            node.select = True
            mat.node_tree.nodes.active = node
            
        # Set the ImageTexture node to be selected
        selectNode(mat, imgTex)
        print("Node selected.")

        # Select objects for bake (HighPoly then LowPoly)
        bpy.ops.object.select_all(action='DESELECT')
        lowPoly.select_set(True)
        highPoly.select_set(True)
        bpy.context.view_layer.objects.active = lowPoly

        # Start the baking process
        print("Begin baking")
        bpy.ops.object.bake(
            type='DIFFUSE', 
            pass_filter={'COLOR'},
            use_selected_to_active=True,
            cage_extrusion=0.1
        )
        print("Bake finished")

        # Use image texture as material base color
        bsdf = mat.node_tree.nodes['Principled BSDF']
        mat.node_tree.links.new(imgTex.outputs['Color'], bsdf.inputs['Base Color'])

        return {'FINISHED'}


class CustomUVOperator(bpy.types.Operator):
    """Custom Wrapper for Smart UV Project. Checks if object has more than 40000 vertices because smart uv project might crash"""
    bl_idname = "object.custom_uv_project"
    bl_label = "Custom UV Project Wrapper Operator"

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        
        lowPoly = bpy.context.active_object
        #UV unwrap the lowPoly mesh
        if len(lowPoly.data.vertices) < 40000:
            print("Vertex count < 40000")
            bpy.ops.object.mode_set(mode='EDIT')
            print(bpy.ops.mesh.select_all(action='SELECT'))
            print("Starting uv unwrap")
            bpy.ops.uv.smart_project()
            bpy.ops.object.editmode_toggle()
            print("Finished uv unwrap")
        else: 
            print("UV unwrap cancelled because of high polygon count: " 
            + str(len(lowPoly.data.vertices)) + " > 40000.")

        return {'FINISHED'}


class OrientByNormalsOperator(bpy.types.Operator):
    """Orients an object so that the average of all selected normals point upwards. 
Select vertices or faces in edit mode and exit to object mode before use"""
    bl_idname = "object.orient_by_normals"
    bl_label = "Orient by Normals Operator"

    # Checks if operator can be executed, returns bool
    @classmethod
    def poll(cls, context):
        if bpy.context.mode != 'OBJECT':
            print("Error: OrientByNormals Operator can only be executed in object mode")
            return False
        return context.active_object is not None


    def execute(self, context):
        object = context.active_object
        
        # Addup normals of selected vertices
        normalAvg = Vector()
        for v in object.data.vertices:
            if v.select:
                print(v.normal)
                normalAvg += v.normal
         
        # Normalize the added normals
        norm = normalAvg / sqrt(normalAvg.x*normalAvg.x + normalAvg.y*normalAvg.y + normalAvg.z*normalAvg.z) 

        # transform normals to world space. @ is character for matrix vector multiplication in blender 2.8+ 
        world_normal = object.matrix_world.inverted().transposed().to_3x3() @ norm

        # Compute rotation quaternion between averaged normal and up vector
        rot = world_normal.rotation_difference(Vector([0, 0, 1]))

        # Set object to use quaternions instead of euler for rotation
        object.rotation_mode = 'QUATERNION'
        # Rotate object so that the averaged normal is pointing upwards
        object.rotation_quaternion = rot @ object.rotation_quaternion
        
        return {'FINISHED'}
    
    
class LowPolyOperator(bpy.types.Operator):
    """Creates a low poly mesh from the selected object by using a decimate with collaps and planar options."""
    bl_idname = "object.create_lowpoly"
    bl_label = "Create low poly copy"

    decimateCollapsValue = bpy.props.FloatProperty(
        name="Decimate Anteil", 
        min = 0, 
        max = 1, 
        default=0.01
    )
    
    decimatePlanarValue = bpy.props.FloatProperty(
        name="Planar Angle", 
        min = 0, 
        default=5
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        
        # Duplicate active object for low poly copy
        highPoly = bpy.context.active_object
        name = highPoly.name 
        
        bpy.ops.object.duplicate()
        lowPoly = bpy.context.active_object
        lowPoly.name = name + "_LowPoly"
        print("Duplicated HighPoly object.") 

        #Reduce polygon count with decimate collaps modifier
        decimate = lowPoly.modifiers.new("Decimate Collaps", 'DECIMATE')
        decimate.ratio = self.decimateCollapsValue
        print("Added decimate modifier.")
        
        res = bpy.ops.object.modifier_apply(modifier="Decimate Collaps")
        print("Applied decimate modifier: " + str(res))

        # Reduce details on even planes (good for buildings)
        planar = lowPoly.modifiers.new("Decimate Planar", 'DECIMATE')
        planar.decimate_type = 'DISSOLVE'
        planar.angle_limit = math.radians(self.decimatePlanarValue)
        print("Added planar modifier.")
        
        res = bpy.ops.object.modifier_apply(modifier="Decimate Planar")
        print("Applied planar modifier: " + str(res))

        return {'FINISHED'}


class PhotogrammetryPanel(bpy.types.Panel):
    """Creates a Panel in the scene context of the properties editor"""
    bl_label = "Photogrammetry Workflow"
    bl_idname = "SCENE_PT_Photogrammetry"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Photogrammerty"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # Orient and center mesh correctly
        layout.label(text="Clean Up")
        
        origin_op = layout.operator("object.origin_set", text='Move to center')
        origin_op.type = 'GEOMETRY_ORIGIN'
        origin_op.center = 'MEDIAN'
        
        layout.operator("object.orient_by_normals", text="Orient by normals")
        
        layout.operator("object.cube_cut", text="Add Cut Bounds").first_call = True
        layout.operator("object.cube_cut", text="Cut Object").first_call = False
        
        # Create Low Poly
        layout.label(text="Create Low Poly")
        
        layout.prop(context.object, "decimateCollaps")
        layout.prop(context.object, "decimatePlanar")
        
        lowpoly_operator = layout.operator("object.create_lowpoly", text="Create Low Poly")
        
        lowpoly_operator.decimateCollapsValue = context.object.decimateCollaps
        lowpoly_operator.decimatePlanarValue = context.object.decimatePlanar
        
        # Smart UV Project
        layout.label(text="Smart UV Project")
        layout.operator("object.custom_uv_project", text="Create UVs")
        
        layout.label(text="Bake Textures")
        layout.operator("object.custom_bake", text="Bake")
        
        

def register(): 
    
    bpy.utils.register_class(CubeCutOperator)
    bpy.utils.register_class(CustomBakeOperator)
    bpy.utils.register_class(CustomUVOperator)
    bpy.utils.register_class(OrientByNormalsOperator)
    bpy.utils.register_class(LowPolyOperator)
    bpy.utils.register_class(PhotogrammetryPanel)
    bpy.types.Object.decimateCollaps = bpy.props.FloatProperty(name="Decimate Anteil", min = 0, max = 1, step=4, precision=4, default=0.01)
    bpy.types.Object.decimatePlanar = bpy.props.FloatProperty(name="Planar Angle", min = 0, default=5)
        
def unregister(): 

    bpy.utils.unregister_class(CubeCutOperator)
    bpy.utils.unregister_class(CustomBakeOperator)
    bpy.utils.unregister_class(CustomUVOperator)
    bpy.utils.unregister_class(OrientByNormalsOperator)
    bpy.utils.unregister_class(LowPolyOperator)
    bpy.utils.unregister_class(PhotogrammetryPanel)
        
if __name__ == "__main__":
    register()