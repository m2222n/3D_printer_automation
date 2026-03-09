# This work is licensed under the MIT license.
# Copyright (c) 2013-2025 OpenMV LLC. All rights reserved.
# https://github.com/openmv/openmv/blob/master/LICENSE
#
# TensorFlow Lite YoloV8 Object Detection Example

import time
import sensor
import ml
from ml.postprocessing import yolo_v8_postprocess
import gc

sensor.reset()
sensor.set_pixformat(sensor.RGB565)
sensor.set_framesize(sensor.VGA)
sensor.set_windowing((400, 400))

import os
print(os.listdir("/rom"))

model = ml.Model("/rom/yolov8n_192_quant_pc_uf_od_coco-person-st.tflite")
model_class_labels = ["person"]
model_class_colors = [(0, 0, 255)]
print(model)

clock = time.clock()
while True:
    clock.tick()
    img = sensor.snapshot()

    # boxes is a list of list per class of ((x, y, w, h), score) tuples
    boxes = model.predict([img], callback=yolo_v8_postprocess(threshold=0.4))

    # Draw bounding boxes around the detected objects
    for i, class_detections in enumerate(boxes):
        rects = [r for r, score in class_detections]
        labels = [model_class_labels[i] for j in range(len(rects))]
        colors = [model_class_colors[i] for j in range(len(rects))]
        ml.utils.draw_predictions(img, rects, labels, colors, format=None)

    print(clock.fps(), "fps")
