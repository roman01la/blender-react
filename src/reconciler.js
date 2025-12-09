import React from "react";
import ReconcilerModule from "react-reconciler";
import { DefaultEventPriority } from "react-reconciler/constants";

// Handle both ESM default export and CommonJS module.exports
const Reconciler = ReconcilerModule.default || ReconcilerModule;

const NoEventPriority = 0;
let currentUpdatePriority = NoEventPriority;

/**
 * Global counter for assigning unique IDs to BlenderNodes.
 */
let nextNodeId = 1;

/**
 * BlenderNode represents a Blender object in our tree.
 * This is what React creates and manipulates through our host config.
 */
class BlenderNode {
  constructor(type, props) {
    this.id = nextNodeId++;
    this.type = type; // "Cube", "Sphere", "Empty", etc.
    this.props = props;
    this.children = [];
    this.parent = null;
    this.blenderName = null; // Name of the object in Blender
  }
}

/**
 * TextNode represents text content (not used much in Blender context)
 */
class TextNode {
  constructor(text) {
    this.id = nextNodeId++;
    this.text = text;
    this.parent = null;
  }
}

/**
 * Send a command to Blender via the applyCommand bridge
 */
function sendCommand(cmd) {
  if (typeof applyCommand === "function") {
    const result = applyCommand(JSON.stringify(cmd));
    return result ? JSON.parse(result) : null;
  }
  console.log("[Blender Command]", JSON.stringify(cmd));
  return null;
}

/**
 * Check if a node type is a material
 */
function isMaterialType(type) {
  const materialTypes = ["material", "standardmaterial", "physicalmaterial"];
  return materialTypes.includes(type.toLowerCase());
}

/**
 * Check if a node type is a geometry nodes modifier
 */
function isGeometryNodesType(type) {
  return type.toLowerCase() === "geometrynodes";
}

/**
 * Check if a node type is a geometry node (inside geometry nodes tree)
 */
function isGeometryNodeType(type) {
  const geoNodeTypes = [
    // Mesh Primitives
    "meshcube",
    "meshcylinder",
    "meshcone",
    "meshsphere",
    "meshicosphere",
    "meshgrid",
    "meshcircle",
    "meshline",
    // Curve Primitives
    "curveline",
    "curvecircle",
    "curvestar",
    "curvespiral",
    "curvequadrilateral",
    "curvebezier",
    // Geometry Operations
    "transform",
    "join",
    "setposition",
    "setshade",
    "subdivide",
    "subdividesurf",
    "extrude",
    "bevel",
    "triangulate",
    "flip",
    "merge",
    "boolean",
    "convexhull",
    "duplicate",
    "delete",
    "separate",
    // Curve Operations
    "curvetomesh",
    "curvetopoints",
    "meshtocurve",
    "fillcurve",
    "fillet",
    "resample",
    "reverse",
    "trim",
    "setsplinetype",
    // Instances
    "instanceonpoints",
    "realizeinstances",
    "rotateinstances",
    "scaleinstances",
    "translateinstances",
    // Input
    "position",
    "normal",
    "index",
    "id",
    "objectinfo",
    "collectioninfo",
    "value",
    "vector",
    "integer",
    "bool",
    "color",
    // Math
    "math",
    "vectormath",
    "compare",
    "clamp",
    "maprange",
    "mix",
    "floattoint",
    "noise",
    "voronoi",
    "gradient",
    "wave",
    "musgrave",
    // Utilities
    "switch",
    "random",
    "combinexyz",
    "separatexyz",
    "alignrotationtovector",
    "rotatevector",
    // Attribute
    "storenameattr",
    "namedattr",
    "captureattr",
    // Material
    "setmaterial",
    "materialindex",
    "setmaterialindex",
  ];
  return geoNodeTypes.includes(type.toLowerCase());
}

/**
 * Create a Blender material
 */
function createBlenderMaterial(node) {
  const { props, id } = node;
  const name = `__blender_mat_${id}`;

  const result = sendCommand({
    type: "create_material",
    name,
    color: props.color,
    metallic: props.metallic,
    roughness: props.roughness,
    emission: props.emission,
    emissionStrength: props.emissionStrength,
    alpha: props.alpha,
    ior: props.ior,
    specular: props.specular,
  });

  if (result) {
    node.blenderName = result.name;
  }
  return result;
}

/**
 * Update a Blender material
 */
function updateBlenderMaterial(node, oldProps, newProps) {
  if (!node.blenderName) return;

  const updates = {};
  let hasUpdates = false;

  const propsToCheck = [
    "color",
    "metallic",
    "roughness",
    "emission",
    "emissionStrength",
    "alpha",
    "ior",
    "specular",
  ];

  for (const prop of propsToCheck) {
    if (
      newProps[prop] !== undefined &&
      JSON.stringify(newProps[prop]) !== JSON.stringify(oldProps[prop])
    ) {
      updates[prop] = newProps[prop];
      hasUpdates = true;
    }
  }

  if (hasUpdates) {
    sendCommand({
      type: "update_material",
      name: node.blenderName,
      ...updates,
    });
  }
}

/**
 * Delete a Blender material
 */
function deleteBlenderMaterial(node) {
  if (!node.blenderName) return;

  sendCommand({
    type: "delete_material",
    name: node.blenderName,
  });
}

/**
 * Assign material to object based on parent-child relationship
 */
function assignMaterialToParent(materialNode) {
  if (!materialNode.blenderName || !materialNode.parent) return;

  const parent = materialNode.parent;
  if (parent instanceof BlenderNode && parent.blenderName) {
    sendCommand({
      type: "set_material",
      object: parent.blenderName,
      material: materialNode.blenderName,
    });
  }
}

// ─────────────────────────────────────────────────────────────────────
// Geometry Nodes Support
// ─────────────────────────────────────────────────────────────────────

/**
 * Create a geometry nodes modifier on parent object
 */
function createGeometryNodesModifier(node) {
  const { props, id } = node;
  const name = `__blender_geonodes_${id}`;

  // Store that we need to create the tree when attached to a mesh
  node.geoNodesName = name;
  node.geoNodesCreated = false;

  return { name };
}

/**
 * Actually create the geometry nodes tree when we know the parent object
 */
function attachGeometryNodesToParent(geoNode) {
  if (geoNode.geoNodesCreated || !geoNode.parent) return;

  const parent = geoNode.parent;
  if (!(parent instanceof BlenderNode) || !parent.blenderName) return;

  const result = sendCommand({
    type: "create_geometry_nodes",
    name: geoNode.geoNodesName,
    object: parent.blenderName,
  });

  if (result) {
    geoNode.blenderName = result.name;
    geoNode.geoNodesCreated = true;

    // Now process all child geometry nodes
    processGeometryNodeChildren(geoNode);
  }
}

/**
 * Process children of a geometry nodes modifier to build the node tree
 *
 * Connection logic:
 * 1. Nodes are connected in sequence by default (node1 -> node2 -> node3 -> output)
 * 2. `connect: "output"` explicitly connects to group output
 * 3. `connect: "nodeName"` connects to a specific node
 * 4. `input: "nodeName"` or `input: "prev"` specifies where input comes from
 * 5. Nodes without geometry output (like Noise) connect their relevant output
 * 6. Nodes passed as props to other nodes are auto-connected to that node's input socket
 */
function processGeometryNodeChildren(geoNodesParent) {
  const treeName = geoNodesParent.blenderName;
  if (!treeName) return;

  // Collect all geometry node children in order (only direct children, not node-as-prop)
  const geoNodes = [];
  const nodesPropCreated = new Set(); // Track nodes created via node-as-prop

  function collectNodes(node) {
    for (const child of node.children) {
      if (child instanceof BlenderNode && isGeometryNodeType(child.type)) {
        geoNodes.push(child);
        // Recurse for nested nodes
        collectNodes(child);
      }
    }
  }

  collectNodes(geoNodesParent);

  if (geoNodes.length === 0) return;

  // Create all nodes first (this also creates node-as-prop children and connects them)
  for (const node of geoNodes) {
    const childNodesCreated = createGeometryNode(treeName, node, geoNodes);
    // Track which nodes were created as props (they're already connected)
    if (childNodesCreated) {
      for (const childNode of childNodesCreated) {
        nodesPropCreated.add(childNode);
      }
    }
  }

  // Determine node categories for smart connection
  const geometryGenerators = [
    "meshcube",
    "meshcylinder",
    "meshcone",
    "meshsphere",
    "meshicosphere",
    "meshgrid",
    "meshcircle",
    "meshline",
    "curveline",
    "curvecircle",
    "curvestar",
    "curvespiral",
    "curvequadrilateral",
    "curvebezier",
  ];

  const geometryProcessors = [
    "transform",
    "join",
    "setposition",
    "setshade",
    "subdivide",
    "subdividesurf",
    "extrude",
    "bevel",
    "triangulate",
    "flip",
    "merge",
    "boolean",
    "convexhull",
    "duplicate",
    "delete",
    "separate",
    "curvetomesh",
    "curvetopoints",
    "meshtocurve",
    "fillcurve",
    "fillet",
    "resample",
    "reverse",
    "trim",
    "setsplinetype",
    "instanceonpoints",
    "realizeinstances",
    "rotateinstances",
    "scaleinstances",
    "translateinstances",
    "setmaterial",
  ];

  const valueNodes = [
    "noise",
    "voronoi",
    "gradient",
    "wave",
    "musgrave",
    "math",
    "vectormath",
    "value",
    "vector",
    "integer",
    "boolean",
    "color",
    "position",
    "normal",
    "index",
    "id",
    "random",
    "combinexyz",
    "separatexyz",
  ];

  // Build connection chain
  // Track the last node that outputs geometry
  let lastGeometryNode = null;

  // Helper to find a node by type name or id
  function findNodeId(name) {
    if (name === "output" || name === "__output__") return "__output__";
    if (name === "input" || name === "__input__") return "__input__";

    // First try exact geoNodeId match
    const exactMatch = geoNodes.find((n) => n.geoNodeId === name);
    if (exactMatch) return exactMatch.geoNodeId;

    // Then try type name match (case insensitive)
    const typeMatch = geoNodes.find(
      (n) => n.type.toLowerCase() === name.toLowerCase()
    );
    if (typeMatch) return typeMatch.geoNodeId;

    // Return as-is (might be a Blender internal node name)
    return name;
  }

  for (let i = 0; i < geoNodes.length; i++) {
    const node = geoNodes[i];

    // Skip nodes that were created as props (they're already connected)
    if (nodesPropCreated.has(node)) {
      continue;
    }

    const typeLower = node.type.toLowerCase();
    const isGenerator = geometryGenerators.includes(typeLower);
    const isProcessor = geometryProcessors.includes(typeLower);
    const isValue = valueNodes.includes(typeLower);

    // Handle explicit connections
    if (node.props.connect) {
      const connect = node.props.connect;
      let toNode, toSocket;

      if (typeof connect === "string") {
        if (connect === "output") {
          toNode = "__output__";
          toSocket = "Geometry";
        } else if (connect.includes(".")) {
          [toNode, toSocket] = connect.split(".");
          toNode = findNodeId(toNode);
        } else {
          toNode = findNodeId(connect);
          toSocket = "Geometry";
        }
      } else if (typeof connect === "object") {
        toNode = findNodeId(connect.node || "output");
        toSocket = connect.socket || "Geometry";
      }

      const fromSocket = node.props.outputSocket || (isValue ? 0 : "Geometry");

      sendCommand({
        type: "connect_geometry_nodes",
        tree: treeName,
        fromNode: node.geoNodeId,
        fromSocket,
        toNode,
        toSocket,
      });

      // If this node outputs geometry and connects to output, it's done
      if (!isValue && toNode === "__output__") {
        lastGeometryNode = null; // Already connected to output
      }
      continue;
    }

    // Handle explicit input connections
    if (node.props.input) {
      const input = node.props.input;
      let fromNode, fromSocket;

      if (input === "prev" && lastGeometryNode) {
        fromNode = lastGeometryNode.geoNodeId;
        fromSocket = "Geometry";
      } else if (typeof input === "string") {
        fromNode = findNodeId(input);
        const sourceNode = geoNodes.find((n) => n.geoNodeId === fromNode);
        fromSocket =
          sourceNode && valueNodes.includes(sourceNode.type.toLowerCase())
            ? 0
            : "Geometry";
      }

      if (fromNode) {
        sendCommand({
          type: "connect_geometry_nodes",
          tree: treeName,
          fromNode,
          fromSocket,
          toNode: node.geoNodeId,
          toSocket: "Geometry",
        });
      }
    }

    // Auto-connect processors to previous geometry node
    if (isProcessor && lastGeometryNode && !node.props.input) {
      sendCommand({
        type: "connect_geometry_nodes",
        tree: treeName,
        fromNode: lastGeometryNode.geoNodeId,
        fromSocket: "Geometry",
        toNode: node.geoNodeId,
        toSocket: "Geometry",
      });
    }

    // Track geometry-outputting nodes
    if (isGenerator || isProcessor) {
      lastGeometryNode = node;
    }
  }

  // Auto-connect last geometry node to output if not already connected
  if (lastGeometryNode) {
    sendCommand({
      type: "connect_geometry_nodes",
      tree: treeName,
      fromNode: lastGeometryNode.geoNodeId,
      fromSocket: "Geometry",
      toNode: "__output__",
      toSocket: "Geometry",
    });
  }
}

/**
 * Check if a value is a React element
 */
function isReactElement(value) {
  return (
    value !== null &&
    typeof value === "object" &&
    (value.$$typeof === Symbol.for("react.element") ||
      value.$$typeof === Symbol.for("react.transitional.element") ||
      // Fallback for environments without Symbol
      (value.type && value.props !== undefined && value.key !== undefined))
  );
}

/**
 * Create a single geometry node in a tree
 * Returns array of additional nodes created from node-as-prop values
 */
function createGeometryNode(treeName, node, allNodes = []) {
  const { type, props, id } = node;
  const nodeId = `__geonode_${id}`;

  // Separate node-as-prop values from regular props
  const regularProps = {};
  const nodeProps = []; // Array of { socketName, reactElement }

  const reservedProps = [
    "connect",
    "outputSocket",
    "children",
    "input",
    "name",
  ];

  for (const [key, value] of Object.entries(props)) {
    if (reservedProps.includes(key)) {
      continue;
    }

    // Check if value is a React element (node-as-prop)
    if (isReactElement(value) && isGeometryNodeType(value.type)) {
      nodeProps.push({ socketName: key, reactElement: value });
    }
    // Check if value is an array of React elements (for multi-input sockets like Join Geometry)
    else if (
      Array.isArray(value) &&
      value.length > 0 &&
      isReactElement(value[0])
    ) {
      for (const elem of value) {
        if (isGeometryNodeType(elem.type)) {
          nodeProps.push({ socketName: key, reactElement: elem });
        }
      }
    } else {
      regularProps[key] = value;
    }
  }

  // Create the main node
  const result = sendCommand({
    type: "add_geometry_node",
    tree: treeName,
    nodeType: type,
    nodeId,
    props: regularProps,
  });

  if (result) {
    node.geoNodeId = result.name;
    node.geoTreeName = treeName;
  }

  // Process node-as-prop children: create BlenderNodes from React elements, then connect
  const createdChildNodes = [];
  for (const { socketName, reactElement } of nodeProps) {
    // Create a BlenderNode from the React element
    const childNode = new BlenderNode(
      reactElement.type,
      reactElement.props || {}
    );

    // Create the geometry node in Blender
    const childCreated = createGeometryNode(treeName, childNode, allNodes);
    createdChildNodes.push(childNode);
    if (childCreated) {
      createdChildNodes.push(...childCreated);
    }

    // Connect child's output to this node's input socket
    if (childNode.geoNodeId) {
      // Determine output socket based on node type
      const childTypeLower = childNode.type.toLowerCase();
      const valueNodes = [
        "noise",
        "voronoi",
        "gradient",
        "wave",
        "musgrave",
        "math",
        "vectormath",
        "value",
        "vector",
        "integer",
        "boolean",
        "color",
        "position",
        "normal",
        "index",
        "id",
        "random",
        "combinexyz",
        "separatexyz",
      ];
      const fromSocket =
        childNode.props.outputSocket ||
        (valueNodes.includes(childTypeLower) ? 0 : "Geometry");

      sendCommand({
        type: "connect_geometry_nodes",
        tree: treeName,
        fromNode: childNode.geoNodeId,
        fromSocket,
        toNode: node.geoNodeId,
        toSocket: socketName,
      });
    }
  }

  return createdChildNodes;
}

/**
 * Update a geometry node's properties
 */
function updateGeometryNode(node, oldProps, newProps) {
  if (!node.geoNodeId || !node.geoTreeName) return;

  const { connect, outputSocket, children, ...nodeProps } = newProps;
  const {
    connect: oldConnect,
    outputSocket: oldOutput,
    children: oldChildren,
    ...oldNodeProps
  } = oldProps;

  // Check what changed
  const updates = {};
  let hasUpdates = false;

  for (const key of Object.keys(nodeProps)) {
    if (JSON.stringify(nodeProps[key]) !== JSON.stringify(oldNodeProps[key])) {
      updates[key] = nodeProps[key];
      hasUpdates = true;
    }
  }

  if (hasUpdates) {
    sendCommand({
      type: "update_geometry_node",
      tree: node.geoTreeName,
      nodeId: node.geoNodeId,
      props: updates,
    });
  }
}

/**
 * Delete a geometry node
 */
function deleteGeometryNode(node) {
  if (!node.geoNodeId || !node.geoTreeName) return;

  sendCommand({
    type: "delete_geometry_node",
    tree: node.geoTreeName,
    nodeId: node.geoNodeId,
  });
}

/**
 * Delete a geometry nodes modifier
 */
function deleteGeometryNodesModifier(node) {
  if (!node.blenderName) return;

  const parentName = node.parent?.blenderName;

  sendCommand({
    type: "delete_geometry_nodes",
    name: node.blenderName,
    object: parentName,
  });
}

/**
 * Create a Blender object based on node type
 */
function createBlenderObject(node) {
  const { type, props, id } = node;

  // Handle materials separately
  if (isMaterialType(type)) {
    return createBlenderMaterial(node);
  }

  // Handle geometry nodes modifier
  if (isGeometryNodesType(type)) {
    return createGeometryNodesModifier(node);
  }

  // Handle geometry node (inside a geometry nodes tree)
  // These are created later when the tree is built
  if (isGeometryNodeType(type)) {
    // Mark as geometry node, will be created when parent tree is processed
    node.isGeoNode = true;
    return { deferred: true };
  }

  // Use internal node id for implicit naming
  const name = `${props.name || "__blender_react_"}${id}`;
  const location = props.position || props.location || [0, 0, 0];
  const rotation = props.rotation || [0, 0, 0];
  const scale = props.scale || [1, 1, 1];

  const typeLower = type.toLowerCase();

  // Check for camera
  if (typeLower === "camera") {
    const result = sendCommand({
      type: "create_camera",
      name,
      location,
      rotation,
      camera_type: props.cameraType || "PERSP", // PERSP, ORTHO, PANO
    });
    if (result) node.blenderName = result.name;
    return result;
  }

  // Check for lights
  const lightTypes = {
    light: "POINT",
    pointlight: "POINT",
    sunlight: "SUN",
    sun: "SUN",
    spotlight: "SPOT",
    spot: "SPOT",
    arealight: "AREA",
    area: "AREA",
  };
  if (lightTypes[typeLower]) {
    const result = sendCommand({
      type: "create_light",
      name,
      location,
      rotation,
      light_type: lightTypes[typeLower],
      energy: props.energy ?? props.intensity ?? 1000,
      color: props.color || [1, 1, 1],
    });
    if (result) node.blenderName = result.name;
    return result;
  }

  // Mesh primitives
  const meshTypes = {
    cube: "cube",
    box: "cube",
    sphere: "uv_sphere",
    uvsphere: "uv_sphere",
    icosphere: "ico_sphere",
    cylinder: "cylinder",
    cone: "cone",
    torus: "torus",
    plane: "plane",
    circle: "circle",
    grid: "grid",
    monkey: "monkey",
    suzanne: "monkey",
  };

  const shape = meshTypes[typeLower];
  if (shape) {
    const result = sendCommand({
      type: "create_primitive",
      shape,
      name,
      location,
      rotation,
      scale,
      // Pass extra props for specific primitives
      segments: props.segments,
      rings: props.rings,
      radius: props.radius,
      depth: props.depth,
      vertices: props.vertices,
    });
    if (result) node.blenderName = result.name;
    return result;
  }

  // Check for empty (useful for grouping)
  if (typeLower === "empty" || typeLower === "group") {
    const result = sendCommand({
      type: "create_empty",
      name,
      location,
      rotation,
      scale,
      empty_type: props.emptyType || "PLAIN_AXES",
    });
    if (result) node.blenderName = result.name;
    return result;
  }

  console.log(`Unknown Blender type: ${type}`);
  return null;
}

/**
 * Update a Blender object's transform
 */
function updateBlenderObject(node, oldProps, newProps) {
  // Handle geometry nodes (inside tree)
  if (isGeometryNodeType(node.type)) {
    updateGeometryNode(node, oldProps, newProps);
    return;
  }

  if (!node.blenderName) return;

  // Handle materials separately
  if (isMaterialType(node.type)) {
    updateBlenderMaterial(node, oldProps, newProps);
    return;
  }

  const updates = {};
  let hasUpdates = false;

  // Check position/location
  const newLoc = newProps.position || newProps.location;
  const oldLoc = oldProps.position || oldProps.location;
  if (newLoc && JSON.stringify(newLoc) !== JSON.stringify(oldLoc)) {
    updates.location = newLoc;
    hasUpdates = true;
  }

  // Check rotation
  if (
    newProps.rotation &&
    JSON.stringify(newProps.rotation) !== JSON.stringify(oldProps.rotation)
  ) {
    updates.rotation_euler = newProps.rotation;
    hasUpdates = true;
  }

  // Check scale
  if (
    newProps.scale &&
    JSON.stringify(newProps.scale) !== JSON.stringify(oldProps.scale)
  ) {
    updates.scale = newProps.scale;
    hasUpdates = true;
  }

  if (hasUpdates) {
    sendCommand({
      type: "set_transform",
      name: node.blenderName,
      ...updates,
    });
  }
}

/**
 * Delete a Blender object
 */
function deleteBlenderObject(node) {
  // Handle geometry node inside tree
  if (isGeometryNodeType(node.type)) {
    deleteGeometryNode(node);
    return;
  }

  // Handle geometry nodes modifier
  if (isGeometryNodesType(node.type)) {
    deleteGeometryNodesModifier(node);
    return;
  }

  if (!node.blenderName) return;

  // Handle materials separately
  if (isMaterialType(node.type)) {
    deleteBlenderMaterial(node);
    return;
  }

  sendCommand({
    type: "delete_object",
    name: node.blenderName,
  });
}

/**
 * Set parent-child relationship in Blender
 */
function setBlenderParent(child, parent) {
  if (!child.blenderName) return;

  const parentName = parent && parent.blenderName ? parent.blenderName : null;

  sendCommand({
    type: "set_parent",
    child: child.blenderName,
    parent: parentName,
  });
}

/**
 * Host Config for React Reconciler - Blender Edition
 */
const hostConfig = {
  // Core creation methods
  createInstance(type, props, rootContainer, hostContext, internalHandle) {
    const node = new BlenderNode(type, props);
    // Create the actual Blender object
    createBlenderObject(node);
    return node;
  },

  createTextInstance(text, rootContainer, hostContext, internalHandle) {
    return new TextNode(text);
  },

  // Tree manipulation methods
  appendInitialChild(parent, child) {
    parent.children.push(child);
    child.parent = parent;
    // If child is a material, assign it to parent mesh
    if (child instanceof BlenderNode && isMaterialType(child.type)) {
      assignMaterialToParent(child);
    }
    // If child is a geometry nodes modifier, attach to parent mesh
    else if (child instanceof BlenderNode && isGeometryNodesType(child.type)) {
      attachGeometryNodesToParent(child);
    }
    // Geometry nodes inside a tree don't need Blender parenting
    else if (child instanceof BlenderNode && isGeometryNodeType(child.type)) {
      // Do nothing - these are handled by the geometry nodes tree
    }
    // Set Blender parent-child relationship for non-special nodes
    else if (
      child instanceof BlenderNode &&
      parent instanceof BlenderNode &&
      !isMaterialType(child.type)
    ) {
      setBlenderParent(child, parent);
    }
  },

  appendChild(parent, child) {
    parent.children.push(child);
    child.parent = parent;
    // If child is a material, assign it to parent mesh
    if (child instanceof BlenderNode && isMaterialType(child.type)) {
      assignMaterialToParent(child);
    }
    // If child is a geometry nodes modifier, attach to parent mesh
    else if (child instanceof BlenderNode && isGeometryNodesType(child.type)) {
      attachGeometryNodesToParent(child);
    }
    // Geometry nodes inside a tree don't need Blender parenting
    else if (child instanceof BlenderNode && isGeometryNodeType(child.type)) {
      // Do nothing - these are handled by the geometry nodes tree
    }
    // Set Blender parent-child relationship for non-special nodes
    else if (
      child instanceof BlenderNode &&
      parent instanceof BlenderNode &&
      !isMaterialType(child.type)
    ) {
      setBlenderParent(child, parent);
    }
  },

  appendChildToContainer(container, child) {
    if (!container.rootChildren) {
      container.rootChildren = [];
    }
    container.rootChildren.push(child);
    child.parent = null;
    // Root children have no Blender parent
    if (child instanceof BlenderNode) {
      setBlenderParent(child, null);
    }
  },

  removeChild(parent, child) {
    const index = parent.children.indexOf(child);
    if (index !== -1) {
      parent.children.splice(index, 1);
    }
    child.parent = null;
    // Delete from Blender
    if (child instanceof BlenderNode) {
      deleteBlenderObject(child);
    }
  },

  removeChildFromContainer(container, child) {
    if (container.rootChildren) {
      const index = container.rootChildren.indexOf(child);
      if (index !== -1) {
        container.rootChildren.splice(index, 1);
      }
    }
    child.parent = null;
    // Delete from Blender
    if (child instanceof BlenderNode) {
      deleteBlenderObject(child);
    }
  },

  insertBefore(parent, child, beforeChild) {
    const index = parent.children.indexOf(beforeChild);
    if (index === -1) {
      parent.children.push(child);
    } else {
      parent.children.splice(index, 0, child);
    }
    child.parent = parent;
  },

  insertInContainerBefore(container, child, beforeChild) {
    if (!container.rootChildren) {
      container.rootChildren = [];
    }
    const index = container.rootChildren.indexOf(beforeChild);
    if (index !== -1) {
      container.rootChildren.splice(index, 0, child);
    } else {
      container.rootChildren.push(child);
    }
    child.parent = null;
  },

  // Update methods
  prepareUpdate(
    instance,
    type,
    oldProps,
    newProps,
    rootContainer,
    hostContext
  ) {
    if (oldProps === newProps) return null;
    if (!oldProps && !newProps) return null;
    if (!oldProps || !newProps) return true;

    const oldKeys = Object.keys(oldProps);
    const newKeys = Object.keys(newProps);

    if (oldKeys.length !== newKeys.length) return true;

    for (const key of newKeys) {
      if (!(key in oldProps)) return true;
      // Deep compare for arrays (position, rotation, scale)
      if (Array.isArray(newProps[key]) && Array.isArray(oldProps[key])) {
        if (JSON.stringify(newProps[key]) !== JSON.stringify(oldProps[key])) {
          return true;
        }
      } else if (oldProps[key] !== newProps[key]) {
        return true;
      }
    }

    return null;
  },

  commitUpdate(instance, type, oldProps, newProps, internalHandle) {
    if (instance instanceof BlenderNode) {
      updateBlenderObject(instance, oldProps, newProps);
    }
    instance.props = newProps;
  },

  commitTextUpdate(textInstance, oldText, newText) {
    textInstance.text = newText;
  },

  // Finalization methods
  finalizeInitialChildren(instance, type, props, rootContainer, hostContext) {
    return false;
  },

  // Context methods
  getRootHostContext(rootContainer) {
    return {};
  },

  getChildHostContext(parentContext, type, rootContainer) {
    return parentContext;
  },

  // Scheduling and lifecycle
  shouldSetTextContent(type, props) {
    return false;
  },

  getPublicInstance(instance) {
    return instance;
  },

  prepareForCommit(containerInfo) {
    return null;
  },

  resetAfterCommit(containerInfo) {
    if (globalThis.blenderApp) {
      globalThis.blenderApp.rootChildren = containerInfo.rootChildren || [];
    }
  },

  preparePortalMount(containerInfo) {},

  scheduleTimeout: setTimeout,
  cancelTimeout: clearTimeout,
  noTimeout: -1,
  isPrimaryRenderer: true,
  supportsMutation: true,
  supportsPersistence: false,
  supportsHydration: false,

  shouldAttemptEagerTransition() {
    return false;
  },

  getCurrentEventPriority() {
    return DefaultEventPriority;
  },

  resolveUpdatePriority() {
    if (currentUpdatePriority !== NoEventPriority) return currentUpdatePriority;
    return DefaultEventPriority;
  },

  getCurrentUpdatePriority() {
    return currentUpdatePriority;
  },

  setCurrentUpdatePriority(newPriority) {
    currentUpdatePriority = newPriority;
  },

  HostTransitionContext: React.createContext(null),

  resolveEventTimeStamp() {
    return -1.1;
  },

  resolveEventType() {
    return null;
  },

  getInstanceFromNode() {
    return null;
  },

  beforeActiveInstanceBlur() {},
  afterActiveInstanceBlur() {},
  prepareScopeUpdate() {},
  getInstanceFromScope() {
    return null;
  },
  detachDeletedInstance() {},

  clearContainer(container) {
    // Delete all Blender objects
    if (container.rootChildren) {
      container.rootChildren.forEach((child) => {
        if (child instanceof BlenderNode) {
          deleteBlenderObject(child);
        }
      });
    }
    container.rootChildren = [];
  },

  trackSchedulerEvent() {},
  rendererVersion: "0.1.0",
  rendererPackageName: "blender-react-reconciler",
};

const reconciler = Reconciler(hostConfig);

if (process.env.NODE_ENV === "development") {
  reconciler.injectIntoDevTools();
}

/**
 * Create a root container for rendering.
 */
export function createRoot() {
  const container = {
    rootChildren: [],
  };

  const fiberRoot = reconciler.createContainer(
    container,
    0, // LegacyRoot
    null,
    false,
    null,
    "",
    (error, errorInfo) => {
      console.log("React Error:", error.message);
      if (errorInfo && errorInfo.componentStack) {
        console.log("Component Stack:", errorInfo.componentStack);
      }
    },
    null
  );

  return { container, fiberRoot };
}

/**
 * Render a React element tree
 */
export function render(element, root) {
  return new Promise((resolve) => {
    reconciler.updateContainer(element, root.fiberRoot, null, () => {
      setTimeout(() => {
        resolve(root.container);
      }, 0);
    });
  });
}

/**
 * Initialize and render the app
 */
export function renderRoot(element, root) {
  globalThis.blenderApp = {
    rootChildren: [],
    render() {
      render(element, root);
    },
  };

  globalThis.blenderApp.render();
}

export { BlenderNode, TextNode };
