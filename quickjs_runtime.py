import bpy
import time

Context = None  # will be filled lazily after import
_install_attempted = False
_runtime = None


def _install_quickjs_via_pip():
    """Try to install the 'quickjs' package into Blender's Python."""
    import sys
    import subprocess

    global _install_attempted
    if _install_attempted:
        return False

    _install_attempted = True

    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "quickjs"])
        print("[QuickJS] Installed 'quickjs' via pip")
        return True
    except Exception as e:
        print(f"[QuickJS] Failed to install 'quickjs': {e}")
        return False


def ensure_quickjs(auto_install: bool = True) -> bool:
    """
    Ensure quickjs.Context is available.
    Returns True if Context is ready, False otherwise.
    """
    global Context

    if Context is not None:
        return True

    # 1) Try import
    try:
        from quickjs import Context as _Context
        Context = _Context
        return True
    except ImportError:
        pass

    # 2) Try auto-install then re-import
    if auto_install:
        if _install_quickjs_via_pip():
            try:
                from quickjs import Context as _Context
                Context = _Context
                return True
            except ImportError as e:
                print(f"[QuickJS] Import still failing after install: {e}")

    return False


def _ensure_websocket_client():
    """Try to install websocket-client package."""
    try:
        import websocket
        return True
    except ImportError:
        pass
    
    import sys
    import subprocess
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client"])
        print("[QuickJS] Installed 'websocket-client' via pip")
        return True
    except Exception as e:
        print(f"[QuickJS] Failed to install 'websocket-client': {e}")
        return False


class QuickJSRuntime:
    def __init__(self):
        if not ensure_quickjs(auto_install=True):
            raise RuntimeError("quickjs module not available (auto-install failed).")
        self.ctx = Context()
        self._timers = {}  # Store timer callbacks
        self._next_timer_id = 1
        self._websockets = {}  # Store WebSocket instances
        self._next_ws_id = 1
        self._install_blender_api()

    def _install_blender_api(self):
        import json
        runtime = self  # Capture self for closures
        
        def debug_print(*args):
            """Print with [JS] prefix for easy filtering."""
            formatted = []
            for arg in args:
                if isinstance(arg, (dict, list)):
                    formatted.append(json.dumps(arg, indent=2))
                else:
                    formatted.append(str(arg))
            print("[JS]", " ".join(formatted))
        
        def console_log(*args):
            """console.log implementation"""
            formatted = [str(arg) for arg in args]
            print("[JS]", " ".join(formatted))
        
        def console_warn(*args):
            """console.warn implementation"""
            formatted = [str(arg) for arg in args]
            print("[JS WARN]", " ".join(formatted))
        
        def console_error(*args):
            """console.error implementation"""
            formatted = [str(arg) for arg in args]
            print("[JS ERROR]", " ".join(formatted))
        
        def debug_inspect(obj):
            """Pretty print an object from JS."""
            print("[JS inspect]", json.dumps(obj, indent=2, default=str))
            return obj  # return it so you can chain: debug_inspect(foo).bar
        
        # Install console callables FIRST
        self.ctx.add_callable("__console_log", console_log)
        self.ctx.add_callable("__console_warn", console_warn)
        self.ctx.add_callable("__console_error", console_error)
        
        # Then create console object polyfill and other globals
        self.ctx.eval("""
            globalThis.console = {
                log: (...args) => __console_log(...args.map(v => v instanceof Error ? v.toString() : v)),
                warn: (...args) => __console_warn(...args.map(v => v instanceof Error ? v.toString() : v)),
                error: (...args) => __console_error(...args.map(v => v instanceof Error ? v.toString() : v)),
                info: (...args) => __console_log(...args.map(v => v instanceof Error ? v.toString() : v)),
                debug: (...args) => __console_log(...args.map(v => v instanceof Error ? v.toString() : v)),
            };
            
            // queueMicrotask polyfill (React needs this)
            if (typeof globalThis.queueMicrotask === 'undefined') {
                globalThis.queueMicrotask = (callback) => {
                    Promise.resolve().then(callback);
                };
            }
        """)
        
        def apply_command(cmd_json):
            # QuickJS passes objects as-is, but complex objects need JSON serialization
            # Accept either a JSON string or try to use directly
            try:
                if isinstance(cmd_json, str):
                    cmd = json.loads(cmd_json)
                else:
                    cmd = cmd_json
                
                kind = cmd.get("type")

                if kind == "create_primitive":
                    shape = cmd["shape"]
                    name = cmd["name"]
                    loc = tuple(cmd.get("location", [0.0, 0.0, 0.0]))
                    rot = tuple(cmd.get("rotation", [0.0, 0.0, 0.0]))
                    scl = tuple(cmd.get("scale", [1.0, 1.0, 1.0]))

                    # Mesh primitives
                    if shape == "cube":
                        bpy.ops.mesh.primitive_cube_add(location=loc, rotation=rot, scale=scl)
                    elif shape == "uv_sphere":
                        segments = cmd.get("segments", 32)
                        rings = cmd.get("rings", 16)
                        bpy.ops.mesh.primitive_uv_sphere_add(location=loc, rotation=rot, scale=scl, segments=segments, ring_count=rings)
                    elif shape == "ico_sphere":
                        subdivisions = cmd.get("subdivisions", 2)
                        bpy.ops.mesh.primitive_ico_sphere_add(location=loc, rotation=rot, scale=scl, subdivisions=subdivisions)
                    elif shape == "cylinder":
                        vertices = cmd.get("vertices", 32)
                        radius = cmd.get("radius", 1.0)
                        depth = cmd.get("depth", 2.0)
                        bpy.ops.mesh.primitive_cylinder_add(location=loc, rotation=rot, scale=scl, vertices=vertices, radius=radius, depth=depth)
                    elif shape == "cone":
                        vertices = cmd.get("vertices", 32)
                        radius1 = cmd.get("radius", 1.0)
                        depth = cmd.get("depth", 2.0)
                        bpy.ops.mesh.primitive_cone_add(location=loc, rotation=rot, scale=scl, vertices=vertices, radius1=radius1, depth=depth)
                    elif shape == "torus":
                        major_radius = cmd.get("radius", 1.0)
                        minor_radius = cmd.get("minor_radius", 0.25)
                        bpy.ops.mesh.primitive_torus_add(location=loc, rotation=rot, major_radius=major_radius, minor_radius=minor_radius)
                    elif shape == "plane":
                        bpy.ops.mesh.primitive_plane_add(location=loc, rotation=rot, scale=scl)
                    elif shape == "circle":
                        vertices = cmd.get("vertices", 32)
                        radius = cmd.get("radius", 1.0)
                        bpy.ops.mesh.primitive_circle_add(location=loc, rotation=rot, vertices=vertices, radius=radius)
                    elif shape == "grid":
                        x_subdivisions = cmd.get("x_subdivisions", 10)
                        y_subdivisions = cmd.get("y_subdivisions", 10)
                        bpy.ops.mesh.primitive_grid_add(location=loc, rotation=rot, x_subdivisions=x_subdivisions, y_subdivisions=y_subdivisions)
                    elif shape == "monkey":
                        bpy.ops.mesh.primitive_monkey_add(location=loc, rotation=rot, scale=scl)
                    else:
                        raise ValueError(f"Unsupported shape: {shape}")

                    obj = bpy.context.active_object
                    obj.name = name
                    return json.dumps({"name": obj.name, "location": list(obj.location)})

                elif kind == "create_camera":
                    name = cmd["name"]
                    loc = tuple(cmd.get("location", [0.0, 0.0, 0.0]))
                    rot = tuple(cmd.get("rotation", [0.0, 0.0, 0.0]))
                    camera_type = cmd.get("camera_type", "PERSP")

                    bpy.ops.object.camera_add(location=loc, rotation=rot)
                    obj = bpy.context.active_object
                    obj.name = name
                    obj.data.type = camera_type
                    return json.dumps({"name": obj.name, "location": list(obj.location)})

                elif kind == "create_light":
                    name = cmd["name"]
                    loc = tuple(cmd.get("location", [0.0, 0.0, 0.0]))
                    rot = tuple(cmd.get("rotation", [0.0, 0.0, 0.0]))
                    light_type = cmd.get("light_type", "POINT")
                    energy = cmd.get("energy", 1000)
                    color = tuple(cmd.get("color", [1.0, 1.0, 1.0]))

                    bpy.ops.object.light_add(type=light_type, location=loc, rotation=rot)
                    obj = bpy.context.active_object
                    obj.name = name
                    obj.data.energy = energy
                    obj.data.color = color
                    return json.dumps({"name": obj.name, "location": list(obj.location)})

                elif kind == "create_empty":
                    name = cmd["name"]
                    loc = tuple(cmd.get("location", [0.0, 0.0, 0.0]))
                    rot = tuple(cmd.get("rotation", [0.0, 0.0, 0.0]))
                    scl = tuple(cmd.get("scale", [1.0, 1.0, 1.0]))
                    empty_type = cmd.get("empty_type", "PLAIN_AXES")

                    bpy.ops.object.empty_add(type=empty_type, location=loc, rotation=rot)
                    obj = bpy.context.active_object
                    obj.name = name
                    obj.scale = scl
                    return json.dumps({"name": obj.name, "location": list(obj.location)})

                elif kind == "set_transform":
                    name = cmd["name"]
                    obj = bpy.data.objects.get(name)
                    if not obj:
                        raise ValueError(f"Object not found: {name}")

                    loc = cmd.get("location")
                    rot = cmd.get("rotation_euler")
                    scale = cmd.get("scale")

                    if loc is not None:
                        obj.location = loc
                    if rot is not None:
                        obj.rotation_euler = rot
                    if scale is not None:
                        obj.scale = scale

                    return json.dumps({"success": True})

                elif kind == "delete_object":
                    name = cmd["name"]
                    obj = bpy.data.objects.get(name)
                    if obj:
                        bpy.data.objects.remove(obj, do_unlink=True)
                    return json.dumps({"success": True})

                elif kind == "set_parent":
                    child_name = cmd["child"]
                    parent_name = cmd.get("parent")  # None means unparent
                    
                    child_obj = bpy.data.objects.get(child_name)
                    if not child_obj:
                        raise ValueError(f"Child object not found: {child_name}")
                    
                    if parent_name:
                        parent_obj = bpy.data.objects.get(parent_name)
                        if not parent_obj:
                            raise ValueError(f"Parent object not found: {parent_name}")
                        
                        # Set parent - child position becomes relative to parent (default Blender behavior)
                        child_obj.parent = parent_obj
                    else:
                        # Unparent
                        child_obj.parent = None
                    
                    return json.dumps({"success": True})

                elif kind == "create_material":
                    name = cmd["name"]
                    
                    # Create new material
                    mat = bpy.data.materials.new(name=name)
                    mat.use_nodes = True
                    
                    # Get the Principled BSDF node
                    bsdf = mat.node_tree.nodes.get("Principled BSDF")
                    if bsdf:
                        # Base color (RGBA)
                        color = cmd.get("color", [0.8, 0.8, 0.8, 1.0])
                        if len(color) == 3:
                            color = list(color) + [1.0]
                        bsdf.inputs["Base Color"].default_value = color
                        
                        # Metallic
                        if "metallic" in cmd:
                            bsdf.inputs["Metallic"].default_value = cmd["metallic"]
                        
                        # Roughness
                        if "roughness" in cmd:
                            bsdf.inputs["Roughness"].default_value = cmd["roughness"]
                        
                        # Emission color
                        if "emission" in cmd:
                            emission = cmd["emission"]
                            if len(emission) == 3:
                                emission = list(emission) + [1.0]
                            bsdf.inputs["Emission Color"].default_value = emission
                        
                        # Emission strength
                        if "emissionStrength" in cmd:
                            bsdf.inputs["Emission Strength"].default_value = cmd["emissionStrength"]
                        
                        # Alpha/transparency
                        if "alpha" in cmd:
                            bsdf.inputs["Alpha"].default_value = cmd["alpha"]
                            mat.blend_method = 'BLEND'
                        
                        # IOR (Index of Refraction)
                        if "ior" in cmd:
                            bsdf.inputs["IOR"].default_value = cmd["ior"]
                        
                        # Specular/Specular IOR Level
                        if "specular" in cmd:
                            # In Blender 4.0+, this is "Specular IOR Level"
                            try:
                                bsdf.inputs["Specular IOR Level"].default_value = cmd["specular"]
                            except KeyError:
                                bsdf.inputs["Specular"].default_value = cmd["specular"]
                    
                    return json.dumps({"name": mat.name})

                elif kind == "update_material":
                    name = cmd["name"]
                    mat = bpy.data.materials.get(name)
                    if not mat:
                        raise ValueError(f"Material not found: {name}")
                    
                    bsdf = mat.node_tree.nodes.get("Principled BSDF")
                    if bsdf:
                        if "color" in cmd:
                            color = cmd["color"]
                            if len(color) == 3:
                                color = list(color) + [1.0]
                            bsdf.inputs["Base Color"].default_value = color
                        if "metallic" in cmd:
                            bsdf.inputs["Metallic"].default_value = cmd["metallic"]
                        if "roughness" in cmd:
                            bsdf.inputs["Roughness"].default_value = cmd["roughness"]
                        if "emission" in cmd:
                            emission = cmd["emission"]
                            if len(emission) == 3:
                                emission = list(emission) + [1.0]
                            bsdf.inputs["Emission Color"].default_value = emission
                        if "emissionStrength" in cmd:
                            bsdf.inputs["Emission Strength"].default_value = cmd["emissionStrength"]
                        if "alpha" in cmd:
                            bsdf.inputs["Alpha"].default_value = cmd["alpha"]
                        if "ior" in cmd:
                            bsdf.inputs["IOR"].default_value = cmd["ior"]
                        if "specular" in cmd:
                            try:
                                bsdf.inputs["Specular IOR Level"].default_value = cmd["specular"]
                            except KeyError:
                                bsdf.inputs["Specular"].default_value = cmd["specular"]
                    
                    return json.dumps({"success": True})

                elif kind == "set_material":
                    obj_name = cmd["object"]
                    mat_name = cmd.get("material")  # None to remove material
                    
                    obj = bpy.data.objects.get(obj_name)
                    if not obj:
                        raise ValueError(f"Object not found: {obj_name}")
                    
                    if mat_name:
                        mat = bpy.data.materials.get(mat_name)
                        if not mat:
                            raise ValueError(f"Material not found: {mat_name}")
                        
                        # Assign material to object
                        if obj.data.materials:
                            obj.data.materials[0] = mat
                        else:
                            obj.data.materials.append(mat)
                    else:
                        # Remove all materials
                        obj.data.materials.clear()
                    
                    return json.dumps({"success": True})

                elif kind == "delete_material":
                    name = cmd["name"]
                    mat = bpy.data.materials.get(name)
                    if mat:
                        bpy.data.materials.remove(mat)
                    return json.dumps({"success": True})

                # ─────────────────────────────────────────────────────────────────────
                # Geometry Nodes Commands
                # ─────────────────────────────────────────────────────────────────────

                elif kind == "create_geometry_nodes":
                    name = cmd["name"]
                    obj_name = cmd["object"]
                    
                    obj = bpy.data.objects.get(obj_name)
                    if not obj:
                        raise ValueError(f"Object not found: {obj_name}")
                    
                    # Check if object can have geometry nodes modifier
                    if obj.type not in ('MESH', 'CURVE', 'SURFACE', 'FONT', 'VOLUME', 'POINTCLOUD'):
                        raise ValueError(f"Object type {obj.type} does not support geometry nodes modifier")
                    
                    # Create new geometry node tree
                    node_tree = bpy.data.node_groups.new(name=name, type='GeometryNodeTree')
                    
                    # Add input and output nodes (required for geometry nodes)
                    input_node = node_tree.nodes.new('NodeGroupInput')
                    input_node.location = (-300, 0)
                    output_node = node_tree.nodes.new('NodeGroupOutput')
                    output_node.location = (300, 0)
                    
                    # Create geometry input/output sockets using the interface API
                    try:
                        # Blender 4.0+ API
                        node_tree.interface.new_socket('Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
                        node_tree.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
                    except AttributeError:
                        # Blender 3.x API fallback
                        node_tree.inputs.new('NodeSocketGeometry', 'Geometry')
                        node_tree.outputs.new('NodeSocketGeometry', 'Geometry')
                    
                    # Add modifier to object
                    modifier = obj.modifiers.new(name=name, type='NODES')
                    if modifier is None:
                        raise ValueError(f"Failed to create geometry nodes modifier on {obj_name}")
                    modifier.node_group = node_tree
                    
                    return json.dumps({"name": node_tree.name, "modifier": modifier.name})

                elif kind == "add_geometry_node":
                    tree_name = cmd["tree"]
                    node_type = cmd["nodeType"]
                    node_id = cmd["nodeId"]
                    props = cmd.get("props", {})
                    
                    tree = bpy.data.node_groups.get(tree_name)
                    if not tree:
                        raise ValueError(f"Node tree not found: {tree_name}")
                    
                    # Map React node types to Blender geometry node types
                    node_type_map = {
                        # Mesh Primitives
                        "meshcube": "GeometryNodeMeshCube",
                        "meshcylinder": "GeometryNodeMeshCylinder",
                        "meshcone": "GeometryNodeMeshCone",
                        "meshsphere": "GeometryNodeMeshUVSphere",
                        "meshicosphere": "GeometryNodeMeshIcoSphere",
                        "meshgrid": "GeometryNodeMeshGrid",
                        "meshcircle": "GeometryNodeMeshCircle",
                        "meshline": "GeometryNodeMeshLine",
                        # Curve Primitives
                        "curveline": "GeometryNodeCurvePrimitiveLine",
                        "curvecircle": "GeometryNodeCurvePrimitiveCircle",
                        "curvestar": "GeometryNodeCurveStar",
                        "curvespiral": "GeometryNodeCurveSpiral",
                        "curvequadrilateral": "GeometryNodeCurvePrimitiveQuadrilateral",
                        "curvebezier": "GeometryNodeCurvePrimitiveBezierSegment",
                        # Geometry Operations
                        "transform": "GeometryNodeTransform",
                        "join": "GeometryNodeJoinGeometry",
                        "setposition": "GeometryNodeSetPosition",
                        "setshade": "GeometryNodeSetShadeSmooth",
                        "subdivide": "GeometryNodeSubdivideMesh",
                        "subdividesurf": "GeometryNodeSubdivisionSurface",
                        "extrude": "GeometryNodeExtrudeMesh",
                        "bevel": "GeometryNodeBevel",
                        "triangulate": "GeometryNodeTriangulate",
                        "flip": "GeometryNodeFlipFaces",
                        "merge": "GeometryNodeMergeByDistance",
                        "boolean": "GeometryNodeMeshBoolean",
                        "convexhull": "GeometryNodeConvexHull",
                        "duplicate": "GeometryNodeDuplicateElements",
                        "delete": "GeometryNodeDeleteGeometry",
                        "separate": "GeometryNodeSeparateGeometry",
                        # Curve Operations
                        "curvetomesh": "GeometryNodeCurveToMesh",
                        "curvetopoints": "GeometryNodeCurveToPoints",
                        "meshtocurve": "GeometryNodeMeshToCurve",
                        "fillcurve": "GeometryNodeFillCurve",
                        "fillet": "GeometryNodeFilletCurve",
                        "resample": "GeometryNodeResampleCurve",
                        "reverse": "GeometryNodeReverseCurve",
                        "trim": "GeometryNodeTrimCurve",
                        "setsplinetype": "GeometryNodeCurveSplineType",
                        # Instances
                        "instanceonpoints": "GeometryNodeInstanceOnPoints",
                        "realizeinstances": "GeometryNodeRealizeInstances",
                        "rotateinstances": "GeometryNodeRotateInstances",
                        "scaleinstances": "GeometryNodeScaleInstances",
                        "translateinstances": "GeometryNodeTranslateInstances",
                        # Input
                        "position": "GeometryNodeInputPosition",
                        "normal": "GeometryNodeInputNormal",
                        "index": "GeometryNodeInputIndex",
                        "id": "GeometryNodeInputID",
                        "objectinfo": "GeometryNodeObjectInfo",
                        "collectioninfo": "GeometryNodeCollectionInfo",
                        "value": "ShaderNodeValue",
                        "vector": "FunctionNodeInputVector",
                        "integer": "FunctionNodeInputInt",
                        "boolean": "FunctionNodeInputBool",
                        "color": "FunctionNodeInputColor",
                        # Math
                        "math": "ShaderNodeMath",
                        "vectormath": "ShaderNodeVectorMath",
                        "compare": "FunctionNodeCompare",
                        "clamp": "ShaderNodeClamp",
                        "maprange": "ShaderNodeMapRange",
                        "mix": "ShaderNodeMix",
                        "floattoint": "FunctionNodeFloatToInt",
                        "noise": "ShaderNodeTexNoise",
                        "voronoi": "ShaderNodeTexVoronoi",
                        "gradient": "ShaderNodeTexGradient",
                        "wave": "ShaderNodeTexWave",
                        "musgrave": "ShaderNodeTexMusgrave",
                        # Utilities
                        "switch": "GeometryNodeSwitch",
                        "random": "FunctionNodeRandomValue",
                        "combineXYZ": "ShaderNodeCombineXYZ",
                        "separatexyz": "ShaderNodeSeparateXYZ",
                        "alignrotationtovector": "FunctionNodeAlignRotationToVector",
                        "rotatevector": "FunctionNodeRotateVector",
                        # Attribute
                        "storenameattr": "GeometryNodeStoreNamedAttribute",
                        "namedattr": "GeometryNodeInputNamedAttribute",
                        "captureattr": "GeometryNodeCaptureAttribute",
                        # Material
                        "setmaterial": "GeometryNodeSetMaterial",
                        "materialindex": "GeometryNodeInputMaterialIndex",
                        "setmaterialindex": "GeometryNodeSetMaterialIndex",
                    }
                    
                    blender_type = node_type_map.get(node_type.lower())
                    if not blender_type:
                        # Try using the type directly (for advanced users)
                        blender_type = node_type
                    
                    node = tree.nodes.new(blender_type)
                    node.name = node_id
                    node.label = props.get("label", "")
                    
                    # Set node location for visual layout
                    if "location" in props:
                        node.location = props["location"]
                    
                    # Set input values from props
                    for key, value in props.items():
                        if key in ("label", "location"):
                            continue
                        # Try to set as input socket
                        if key in node.inputs:
                            try:
                                node.inputs[key].default_value = value
                            except:
                                pass
                        # Try to set as node property
                        elif hasattr(node, key):
                            try:
                                setattr(node, key, value)
                            except:
                                pass
                    
                    return json.dumps({"name": node.name})

                elif kind == "connect_geometry_nodes":
                    tree_name = cmd["tree"]
                    from_node = cmd["fromNode"]
                    from_socket = cmd["fromSocket"]
                    to_node = cmd["toNode"]
                    to_socket = cmd["toSocket"]
                    
                    tree = bpy.data.node_groups.get(tree_name)
                    if not tree:
                        raise ValueError(f"Node tree not found: {tree_name}")
                    
                    # Handle special node names
                    if from_node == "__input__":
                        source = tree.nodes.get("Group Input")
                    else:
                        source = tree.nodes.get(from_node)
                    
                    if to_node == "__output__":
                        target = tree.nodes.get("Group Output")
                    else:
                        target = tree.nodes.get(to_node)
                    
                    if not source:
                        raise ValueError(f"Source node not found: {from_node}")
                    if not target:
                        raise ValueError(f"Target node not found: {to_node}")
                    
                    # Get output socket by name or index
                    out_socket = None
                    if isinstance(from_socket, int):
                        out_socket = source.outputs[from_socket]
                    elif isinstance(from_socket, str):
                        if from_socket in source.outputs:
                            out_socket = source.outputs[from_socket]
                        elif from_socket.isdigit():
                            out_socket = source.outputs[int(from_socket)]
                        else:
                            # Default to first output
                            out_socket = source.outputs[0] if len(source.outputs) > 0 else None
                    
                    # Get input socket by name or index
                    in_socket = None
                    if isinstance(to_socket, int):
                        in_socket = target.inputs[to_socket]
                    elif isinstance(to_socket, str):
                        if to_socket in target.inputs:
                            in_socket = target.inputs[to_socket]
                        elif to_socket.isdigit():
                            in_socket = target.inputs[int(to_socket)]
                        else:
                            # Default to first input
                            in_socket = target.inputs[0] if len(target.inputs) > 0 else None
                    
                    if not out_socket:
                        raise ValueError(f"Output socket not found: {from_socket} on {from_node}")
                    if not in_socket:
                        raise ValueError(f"Input socket not found: {to_socket} on {to_node}")
                    
                    tree.links.new(out_socket, in_socket)
                    return json.dumps({"success": True})

                elif kind == "update_geometry_node":
                    tree_name = cmd["tree"]
                    node_id = cmd["nodeId"]
                    props = cmd.get("props", {})
                    
                    tree = bpy.data.node_groups.get(tree_name)
                    if not tree:
                        raise ValueError(f"Node tree not found: {tree_name}")
                    
                    node = tree.nodes.get(node_id)
                    if not node:
                        raise ValueError(f"Node not found: {node_id}")
                    
                    # Update input values
                    for key, value in props.items():
                        if key in ("label", "location"):
                            if key == "label":
                                node.label = value
                            continue
                        if key in node.inputs:
                            try:
                                node.inputs[key].default_value = value
                            except:
                                pass
                        elif hasattr(node, key):
                            try:
                                setattr(node, key, value)
                            except:
                                pass
                    
                    return json.dumps({"success": True})

                elif kind == "delete_geometry_node":
                    tree_name = cmd["tree"]
                    node_id = cmd["nodeId"]
                    
                    tree = bpy.data.node_groups.get(tree_name)
                    if not tree:
                        return json.dumps({"success": True})  # Tree already gone
                    
                    node = tree.nodes.get(node_id)
                    if node:
                        tree.nodes.remove(node)
                    
                    return json.dumps({"success": True})

                elif kind == "delete_geometry_nodes":
                    name = cmd["name"]
                    obj_name = cmd.get("object")
                    
                    # Remove modifier from object if specified
                    if obj_name:
                        obj = bpy.data.objects.get(obj_name)
                        if obj:
                            for mod in obj.modifiers:
                                if mod.type == 'NODES' and mod.node_group and mod.node_group.name == name:
                                    obj.modifiers.remove(mod)
                                    break
                    
                    # Remove node tree
                    tree = bpy.data.node_groups.get(name)
                    if tree:
                        bpy.data.node_groups.remove(tree)
                    
                    return json.dumps({"success": True})

                else:
                    raise ValueError(f"Unknown command type: {kind}")
            
            except Exception as e:
                print(f"[applyCommand error] {e}")
                raise

        # Timer implementation using Blender timers
        def set_timeout(callback, delay_ms):
            """setTimeout implementation for QuickJS"""
            timer_id = runtime._next_timer_id
            runtime._next_timer_id += 1
            
            def timer_callback():
                if timer_id in runtime._timers:
                    del runtime._timers[timer_id]
                    try:
                        callback()
                    except Exception as e:
                        print(f"[setTimeout error] {e}")
                return None  # Don't repeat
            
            runtime._timers[timer_id] = timer_callback
            bpy.app.timers.register(timer_callback, first_interval=delay_ms / 1000.0)
            return timer_id

        def set_interval(callback, delay_ms):
            """setInterval implementation for QuickJS"""
            timer_id = runtime._next_timer_id
            runtime._next_timer_id += 1
            interval_sec = delay_ms / 1000.0
            
            def timer_callback():
                if timer_id not in runtime._timers:
                    return None  # Stop if cleared
                try:
                    callback()
                except Exception as e:
                    print(f"[setInterval error] {e}")
                    return None  # Stop on error
                return interval_sec  # Repeat
            
            runtime._timers[timer_id] = timer_callback
            bpy.app.timers.register(timer_callback, first_interval=interval_sec)
            return timer_id

        def clear_timeout(timer_id):
            """clearTimeout implementation for QuickJS"""
            if timer_id in runtime._timers:
                callback = runtime._timers.pop(timer_id)
                if bpy.app.timers.is_registered(callback):
                    bpy.app.timers.unregister(callback)

        def clear_interval(timer_id):
            """clearInterval implementation for QuickJS"""
            clear_timeout(timer_id)  # Same logic

        # ─────────────────────────────────────────────────────────────────────
        # requestAnimationFrame implementation
        # ─────────────────────────────────────────────────────────────────────
        
        _raf_callbacks = {}
        _next_raf_id = [1]  # Use list to allow mutation in closure
        _raf_running = [False]
        _pending_rafs = []
        
        def raf_loop():
            """Main animation frame loop"""
            if not _raf_running[0]:
                return None  # Stop the loop
            
            # Process all pending callbacks
            callbacks_to_run = list(_pending_rafs)
            _pending_rafs.clear()
            
            for raf_id, callback in callbacks_to_run:
                if raf_id in _raf_callbacks:
                    del _raf_callbacks[raf_id]
                    try:
                        # Pass a timestamp (milliseconds since start)
                        timestamp = time.time() * 1000
                        callback(timestamp)
                    except Exception as e:
                        print(f"[requestAnimationFrame error] {e}")
            
            # Continue loop if there are pending callbacks or if explicitly running
            if _pending_rafs or _raf_callbacks:
                return 1/60  # ~60 FPS
            else:
                _raf_running[0] = False
                return None
        
        def request_animation_frame(callback):
            """requestAnimationFrame implementation for QuickJS"""
            raf_id = _next_raf_id[0]
            _next_raf_id[0] += 1
            
            _raf_callbacks[raf_id] = callback
            _pending_rafs.append((raf_id, callback))
            
            # Start the loop if not already running
            if not _raf_running[0]:
                _raf_running[0] = True
                bpy.app.timers.register(raf_loop, first_interval=1/60)
            
            return raf_id
        
        def cancel_animation_frame(raf_id):
            """cancelAnimationFrame implementation for QuickJS"""
            if raf_id in _raf_callbacks:
                del _raf_callbacks[raf_id]
            # Remove from pending list too
            for i, (id_, _) in enumerate(_pending_rafs):
                if id_ == raf_id:
                    _pending_rafs.pop(i)
                    break

        # ─────────────────────────────────────────────────────────────────────
        # WebSocket implementation
        # ─────────────────────────────────────────────────────────────────────
        
        def ws_create(url):
            """Create a new WebSocket connection"""
            if not _ensure_websocket_client():
                raise RuntimeError("websocket-client not available")
            
            import websocket
            import threading
            import queue
            
            ws_id = runtime._next_ws_id
            runtime._next_ws_id += 1
            
            # Message queue for thread-safe communication
            msg_queue = queue.Queue()
            
            ws_state = {
                "ws": None,
                "ready_state": 0,  # 0=CONNECTING, 1=OPEN, 2=CLOSING, 3=CLOSED
                "queue": msg_queue,
                "callbacks": {
                    "onopen": None,
                    "onmessage": None,
                    "onerror": None,
                    "onclose": None,
                },
                "poll_timer": None,
            }
            
            def on_open(ws):
                msg_queue.put(("open", None))
            
            def on_message(ws, message):
                msg_queue.put(("message", message))
            
            def on_error(ws, error):
                msg_queue.put(("error", str(error)))
            
            def on_close(ws, close_status_code, close_msg):
                msg_queue.put(("close", {"code": close_status_code, "reason": close_msg}))
            
            def run_websocket():
                try:
                    ws = websocket.WebSocketApp(
                        url,
                        on_open=on_open,
                        on_message=on_message,
                        on_error=on_error,
                        on_close=on_close,
                    )
                    ws_state["ws"] = ws
                    ws.run_forever()
                except Exception as e:
                    msg_queue.put(("error", str(e)))
                finally:
                    ws_state["ready_state"] = 3
            
            # Start WebSocket in a background thread
            thread = threading.Thread(target=run_websocket, daemon=True)
            thread.start()
            
            # Poll for messages using Blender timer
            def poll_messages():
                if ws_id not in runtime._websockets:
                    return None  # Stop polling
                
                state = runtime._websockets[ws_id]
                try:
                    while True:
                        try:
                            event_type, data = state["queue"].get_nowait()
                            
                            if event_type == "open":
                                state["ready_state"] = 1
                                cb = state["callbacks"]["onopen"]
                                if cb:
                                    try:
                                        cb()
                                    except Exception as e:
                                        print(f"[WebSocket onopen error] {e}")
                            
                            elif event_type == "message":
                                cb = state["callbacks"]["onmessage"]
                                if cb:
                                    try:
                                        cb(data)
                                    except Exception as e:
                                        print(f"[WebSocket onmessage error] {e}")
                            
                            elif event_type == "error":
                                cb = state["callbacks"]["onerror"]
                                if cb:
                                    try:
                                        cb(data)
                                    except Exception as e:
                                        print(f"[WebSocket onerror error] {e}")
                            
                            elif event_type == "close":
                                state["ready_state"] = 3
                                cb = state["callbacks"]["onclose"]
                                if cb:
                                    try:
                                        cb(data.get("code"), data.get("reason"))
                                    except Exception as e:
                                        print(f"[WebSocket onclose error] {e}")
                                return None  # Stop polling on close
                                
                        except queue.Empty:
                            break
                except Exception as e:
                    print(f"[WebSocket poll error] {e}")
                
                return 0.01  # Poll every 10ms
            
            ws_state["poll_timer"] = poll_messages
            bpy.app.timers.register(poll_messages, first_interval=0.01)
            
            runtime._websockets[ws_id] = ws_state
            return ws_id
        
        def ws_send(ws_id, data):
            """Send data through WebSocket"""
            if ws_id not in runtime._websockets:
                raise ValueError(f"WebSocket {ws_id} not found")
            
            state = runtime._websockets[ws_id]
            ws = state.get("ws")
            if ws and state["ready_state"] == 1:
                ws.send(data)
        
        def ws_close(ws_id, code=1000, reason=""):
            """Close WebSocket connection"""
            if ws_id not in runtime._websockets:
                return
            
            state = runtime._websockets[ws_id]
            state["ready_state"] = 2
            ws = state.get("ws")
            if ws:
                ws.close(close_status_code=code, close_reason=reason)
        
        def ws_set_callback(ws_id, event_name, callback):
            """Set a callback for WebSocket events"""
            if ws_id not in runtime._websockets:
                raise ValueError(f"WebSocket {ws_id} not found")
            
            state = runtime._websockets[ws_id]
            if event_name in state["callbacks"]:
                state["callbacks"][event_name] = callback
        
        def ws_get_ready_state(ws_id):
            """Get WebSocket ready state"""
            if ws_id not in runtime._websockets:
                return 3  # CLOSED
            return runtime._websockets[ws_id]["ready_state"]
        
        def get_time():
            """Get current time in milliseconds since epoch"""
            return time.time() * 1000

        # Expose functions to JS
        self.ctx.add_callable("applyCommand", apply_command)
        self.ctx.add_callable("print", debug_print)
        self.ctx.add_callable("inspect", debug_inspect)
        self.ctx.add_callable("setTimeout", set_timeout)
        self.ctx.add_callable("setInterval", set_interval)
        self.ctx.add_callable("clearTimeout", clear_timeout)
        self.ctx.add_callable("clearInterval", clear_interval)
        self.ctx.add_callable("requestAnimationFrame", request_animation_frame)
        self.ctx.add_callable("cancelAnimationFrame", cancel_animation_frame)
        self.ctx.add_callable("getTime", get_time)
        
        # WebSocket functions
        self.ctx.add_callable("__ws_create", ws_create)
        self.ctx.add_callable("__ws_send", ws_send)
        self.ctx.add_callable("__ws_close", ws_close)
        self.ctx.add_callable("__ws_set_callback", ws_set_callback)
        self.ctx.add_callable("__ws_get_ready_state", ws_get_ready_state)
        
        # Install WebSocket class polyfill
        self.ctx.eval("""
            globalThis.WebSocket = class WebSocket {
                static CONNECTING = 0;
                static OPEN = 1;
                static CLOSING = 2;
                static CLOSED = 3;
                
                constructor(url) {
                    this._id = __ws_create(url);
                    this._onopen = null;
                    this._onmessage = null;
                    this._onerror = null;
                    this._onclose = null;
                    
                    // Set up callbacks
                    __ws_set_callback(this._id, "onopen", () => {
                        if (this._onopen) this._onopen({ type: "open" });
                    });
                    __ws_set_callback(this._id, "onmessage", (data) => {
                        if (this._onmessage) this._onmessage({ type: "message", data });
                    });
                    __ws_set_callback(this._id, "onerror", (error) => {
                        if (this._onerror) this._onerror({ type: "error", error });
                    });
                    __ws_set_callback(this._id, "onclose", (code, reason) => {
                        if (this._onclose) this._onclose({ type: "close", code, reason });
                    });
                }
                
                get readyState() {
                    return __ws_get_ready_state(this._id);
                }
                
                get onopen() { return this._onopen; }
                set onopen(fn) { this._onopen = fn; }
                
                get onmessage() { return this._onmessage; }
                set onmessage(fn) { this._onmessage = fn; }
                
                get onerror() { return this._onerror; }
                set onerror(fn) { this._onerror = fn; }
                
                get onclose() { return this._onclose; }
                set onclose(fn) { this._onclose = fn; }
                
                send(data) {
                    __ws_send(this._id, data);
                }
                
                close(code = 1000, reason = "") {
                    __ws_close(this._id, code, reason);
                }
            };
            
            WebSocket.CONNECTING = 0;
            WebSocket.OPEN = 1;
            WebSocket.CLOSING = 2;
            WebSocket.CLOSED = 3;
        """)

    def eval_js(self, code: str):
        """Evaluate JS code in this QuickJS context."""
        return self.ctx.eval(code)

    def load_file(self, filepath: str):
        """Load and execute a JS file in this QuickJS context."""
        import os
        
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"JS file not found: {filepath}")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            code = f.read()
        
        return self.eval_js(code)


def get_runtime() -> QuickJSRuntime:
    """
    Get (or create) the global QuickJSRuntime.
    Auto-installs quickjs if needed.
    """
    global _runtime
    if _runtime is None:
        _runtime = QuickJSRuntime()
    return _runtime


def eval_js(code: str):
    """
    Convenience helper: evaluate JS in the global runtime.
    """
    rt = get_runtime()
    return rt.eval_js(code)


def load_plugin(plugin_path: str = None):
    """
    Load the bundle.js file into the global QuickJS runtime.
    If plugin_path is not provided, uses 'bundle.js' in the current directory.
    """
    if plugin_path is None:
        import os
        plugin_path = os.path.join(os.path.dirname(__file__), "bundle.js")
    
    rt = get_runtime()
    return rt.load_file(plugin_path)


def reload():
    """
    Reset the QuickJS runtime and reload bundle.js.
    Useful during development to pick up JS changes without restarting Blender.
    """
    global _runtime
    _runtime = None  # discard old context
    _runtime = QuickJSRuntime()  # create fresh context
    load_plugin()
    print("[QuickJS] Runtime reloaded.")
    return _runtime


# ─────────────────────────────────────────────────────────────────────────────
# Blender Operator for reloading (can be bound to a hotkey or menu)
# ─────────────────────────────────────────────────────────────────────────────

class QUICKJS_OT_reload(bpy.types.Operator):
    """Reload QuickJS runtime and bundle.js"""
    bl_idname = "quickjs.reload"
    bl_label = "Reload QuickJS Plugin"

    def execute(self, context):
        try:
            reload()
            self.report({'INFO'}, "QuickJS plugin reloaded")
        except Exception as e:
            self.report({'ERROR'}, f"Reload failed: {e}")
        return {'FINISHED'}


def register_operators():
    bpy.utils.register_class(QUICKJS_OT_reload)


def unregister_operators():
    bpy.utils.unregister_class(QUICKJS_OT_reload)

