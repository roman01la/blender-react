(ns app.core
  (:require [uix.core :as uix :refer [$ defui defhook]]
            [blender.client :as bc]))

(defhook use-frame [f]
  (let [f* (uix/use-effect-event f)]
    (uix/use-effect
      (fn []
        (let [raf-id (atom nil)
              time (atom (js/getTime))
              animate (fn animate [t]
                        (f* (- t @time))
                        (reset! time t)
                        (reset! raf-id (js/requestAnimationFrame animate)))]
          (reset! raf-id (js/requestAnimationFrame animate))
          #(js/cancelAnimationFrame @raf-id)))
      [])))

(defui spinning-cube []
  (let [[rotation set-rotation] (uix/use-state 0)]
    (use-frame
      (fn [dt]
        (set-rotation + (* dt 0.005))))
    ($ :cube {:position #js [-4 0 4]
              :rotation #js [0 0 rotation]}
      ;; Material as child of mesh - gets auto-assigned
      ($ :material {:color #js [0 0.5 0.2]
                    :metallic 0
                    :roughness 0.2}))))

(defui app []
  ($ :<>
    ;; Animated spinning cube with red metallic material
    ($ spinning-cube)
    
    ;; ===== GEOMETRY NODES EXAMPLES =====
    ;; Procedural grid - simple chain: meshGrid -> setPosition -> output
    ($ :cube {:position #js [-4 0 0] :scale #js [0.1 0.1 0.1]}
      ($ :geometryNodes
        ;; Create a grid (geometry generator)
        ($ :meshGrid {"Size X" 4 "Size Y" 4 "Vertices X" 10 "Vertices Y" 10})
        ;; Set position processes the geometry and auto-connects to output
        ($ :setPosition {})))
    
    ;; Scatter instances on a surface
    ($ :plane {:position #js [-4 4 0] :scale #js [0.1 0.1 0.1]}
      ($ :geometryNodes
        ;; Create base grid
        ($ :meshGrid {"Size X" 5 "Size Y" 5 "Vertices X" 20 "Vertices Y" 20})
        ;; Instance points on the grid
        ($ :instanceOnPoints {})
        ;; What to instance (needs to connect to Instance input)
        ($ :meshCube {:Size #js [0.1 0.1 0.1] :connect {:node "instanceOnPoints" :socket "Instance"}})))
    
    ;; Curved line to mesh (pipe/tube)
    ($ :cube {:position #js [-4 -4 0] :scale #js [0.1 0.1 0.1]}
      ($ :geometryNodes
        ;; Create a spiral curve
        ($ :curveSpiral {:Rotations 9 :Height 4.0})
        ;; Convert curve to mesh with a profile
        ($ :curveToMesh {})
        ;; Profile circle connects to Profile Curve input
        ($ :curveCircle {:Radius 0.1 :connect {:node "curveToMesh" :socket "Profile Curve"}})))
    
    ;; ===== MATERIALS ON MESHES =====
    ;; Blue glossy sphere
    ($ :sphere {:position #js [3 0 0] :segments 32 :rings 16}
      ($ :material {:color #js [0.2 0.4 1.0]
                    :metallic 0.9
                    :roughness 0.1}))
    
    ;; Gold metallic icosphere
    ($ :icosphere {:position #js [6 0 0] :subdivisions 2}
      ($ :material {:color #js [1.0 0.84 0.0]
                    :metallic 1.0
                    :roughness 0.3}))
    
    ;; Green emissive cylinder (glowing)
    ($ :cylinder {:position #js [0 3 0] :radius 0.5 :depth 2 :vertices 32}
      ($ :material {:color #js [0.1 0.1 0.1]
                    :emission #js [0.0 1.0 0.2]
                    :emissionStrength 5.0}))
    
    ;; Purple matte cone
    ($ :cone {:position #js [3 3 0] :radius 0.5 :depth 2}
      ($ :material {:color #js [0.6 0.2 0.8]
                    :roughness 0.9
                    :metallic 0.0}))
    
    ;; Semi-transparent plane (glass-like)
    ($ :plane {:position #js [6 3 0] :scale #js [2 2 1]}
      ($ :material {:color #js [0.9 0.9 1.0]
                    :alpha 0.3
                    :roughness 0.0
                    :metallic 0.0}))
    
    ;; Orange torus
    ($ :torus {:position #js [0 6 0] :radius 1 :minor-radius 0.3}
      ($ :material {:color #js [1.0 0.5 0.0]
                    :metallic 0.5
                    :roughness 0.4}))
    
    ;; Chrome Suzanne
    ($ :monkey {:position #js [3 6 0] :scale #js [0.5 0.5 0.5]}
      ($ :material {:color #js [0.9 0.9 0.9]
                    :metallic 1.0
                    :roughness 0.0
                    :specular 1.0}))
    
    ;; ===== LIGHTS =====
    ($ :pointLight {:position #js [0 0 5] :energy 1000 :color #js [1 1 1]})
    ($ :sunLight {:position #js [5 5 10] :energy 5 :rotation #js [-0.5 0.5 0]})
    ($ :spotLight {:position #js [-5 0 5] :energy 2000 :rotation #js [1 0 0]})
    ($ :areaLight {:position #js [5 -5 3] :energy 500})
    
    ;; ===== CAMERA =====
    ($ :camera {:position #js [10 -10 8] :rotation #js [1.0 0 0.8]})
    
    ;; ===== EMPTY (for grouping/organization) =====
    ($ :empty {:position #js [0 0 3]}
      ;; Child objects of the empty - both with materials
      ($ :cube {:position #js [1 0 0] :scale #js [0.5 0.5 0.5]}
        ($ :material {:color #js [1.0 0.0 0.0] :roughness 0.5}))
      ($ :sphere {:position #js [-1 0 0] :scale #js [0.5 0.5 0.5]}
        ($ :material {:color #js [0.0 0.0 1.0] :roughness 0.5})))))

(defn init []
  (bc/render #'app))