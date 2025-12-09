(ns blender.client
  (:require ["../reconciler.js" :as r]
            [blender.repl.client]
            [uix.core :refer [$]]))

(defn render [component-var]
  (r/renderRoot ($ @component-var) (r/createRoot)))
