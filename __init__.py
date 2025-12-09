bl_info = {
    "name": "Blender React",
    "author": "Roman Liutikov",
    "version": (0, 1, 0),
    "blender": (3, 0, 0),
    "location": "Nowhere (headless service)",
    "description": "Manage Blender scenes via React",
    "category": "System",
}

import bpy
from . import quickjs_runtime


def _clear_default_scene():
    """Remove default Blender objects (Cube, Light, Camera)."""
    default_objects = ["Cube", "Light", "Camera"]
    for name in default_objects:
        obj = bpy.data.objects.get(name)
        if obj:
            bpy.data.objects.remove(obj, do_unlink=True)
    print("[QuickJS] Cleared default scene objects.")


def _deferred_init():
    """Called by timer after Blender is fully initialized."""
    try:
        _clear_default_scene()
        quickjs_runtime.get_runtime()
        quickjs_runtime.load_plugin()
        print("[QuickJS] Runtime initialized.")
    except Exception as e:
        print(f"[QuickJS] Failed to initialize runtime: {e}")
    return None  # Don't repeat the timer


def register():
    # Register operators first
    quickjs_runtime.register_operators()
    
    # Defer plugin loading until Blender is fully ready (0.1 second delay)
    bpy.app.timers.register(_deferred_init, first_interval=0.1)


def unregister():
    # Unregister timer if still pending
    if bpy.app.timers.is_registered(_deferred_init):
        bpy.app.timers.unregister(_deferred_init)
    
    quickjs_runtime.unregister_operators()
    # Nothing special to clean up for now; runtime will be GC'd.
    print("[QuickJS] Runtime addon unloaded.")
