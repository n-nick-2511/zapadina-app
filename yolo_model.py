import os
import cv2
import numpy as np

images_dir = r"D:/Users/n_nick/НИР/yolo_export/images"
labels_dir = r"D:/Users/n_nick/НИР/yolo_export/labels"
output_dir = r"D:/Users/n_nick/НИР/yolo_export/visualized"

os.makedirs(output_dir, exist_ok=True)

for img_name in os.listdir(images_dir):

    if not img_name.lower().endswith((".png", ".jpg", ".jpeg")):
        continue

    img_path = os.path.join(images_dir, img_name)

    label_path = os.path.join(
        labels_dir,
        os.path.splitext(img_name)[0] + ".txt"
    )

    # ===== НАДЁЖНАЯ ЗАГРУЗКА (Windows + UTF-8 safe) =====
    img = cv2.imdecode(
        np.fromfile(img_path, dtype=np.uint8),
        cv2.IMREAD_COLOR
    )

    if img is None:
        print("❌ не открылось:", img_path)
        continue

    h, w = img.shape[:2]

    # если нет разметки — просто сохраняем
    if not os.path.exists(label_path):
        cv2.imwrite(os.path.join(output_dir, img_name), img)
        continue

    with open(label_path, "r") as f:
        lines = f.readlines()

    for line in lines:
        parts = list(map(float, line.strip().split()))

        # поддержка формата с confidence и без
        if len(parts) == 6:
            cls, conf, x_c, y_c, bw, bh = parts
        else:
            cls, x_c, y_c, bw, bh = parts
            conf = None

        # # YOLO → pixel coords
        x_c *= w
        y_c *= h
        bw *= w
        bh *= h

        print("bbox:", cls, x_c, y_c, bw, bh)

        x1 = int(x_c - bw / 2)
        y1 = int(y_c - bh / 2)
        x2 = int(x_c + bw / 2)
        y2 = int(y_c + bh / 2)

        # рисуем bbox
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 2)


        # подпись
        label = str(int(cls))
        if conf is not None:
            label += f" {conf:.2f}"

        cv2.putText(
            img,
            label,
            (x1, max(0, y1 - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 0, 255),
            1,
            cv2.LINE_AA
        )

    out_path = os.path.join(output_dir, img_name)
    ok = cv2.imwrite(out_path, img)
    print("saved:", out_path, "OK:", ok)

    # cv2.imwrite(os.path.join(output_dir, img_name), img)

print("✅ Готово")