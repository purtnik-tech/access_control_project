import json
import cv2
from pathlib import Path

DATASET_DIR = "C:\\license_plates_dataset"
SPLITS = ["train", "val", "test"]


def convert_bbox(img_w, img_h, x, y, w, h):
    xc = (x + w / 2) / img_w
    yc = (y + h / 2) / img_h
    bw = w / img_w
    bh = h / img_h
    return xc, yc, bw, bh


def safe_get_bbox(obj):
    """
    Пытаемся достать bbox из разных форматов
    """
    if not obj:
        return None

    if bb := obj.get("bbox"):
        return bb

    if all(k in obj for k in ["x", "y", "width", "height"]):
        return obj["x"], obj["y"], obj["width"], obj["height"]

    return None


for split in SPLITS:
    img_dir = Path(DATASET_DIR) / split / "img"
    ann_dir = Path(DATASET_DIR) / split / "ann"
    label_dir = Path(DATASET_DIR) / "labels" / split

    label_dir.mkdir(parents=True, exist_ok=True)

    for json_path in ann_dir.glob("*.json"):
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        image_name = json_path.stem + ".jpg"
        image_path = img_dir / image_name

        img = cv2.imread(str(image_path))
        if img is None:
            print(f"[SKIP] missing image: {image_name}")
            continue

        h_img, w_img = img.shape[:2]

        label_path = label_dir / f"{json_path.stem}.txt"

        with open(label_path, "w") as out:

            objects = data.get("objects", [])

            # CASE 1: есть bbox-объекты
            if objects and any(safe_get_bbox(o) for o in objects):

                for obj in objects:
                    bbox = safe_get_bbox(obj)
                    if bbox is None:
                        continue

                    x, y, w, h = bbox

                    if w < 2 or h < 2:
                        continue

                    xc, yc, bw, bh = convert_bbox(w_img, h_img, x, y, w, h)

                    out.write(f"0 {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}\n")

            # CASE 2: bbox отсутствует → считаем весь image объектом
            else:
                out.write("0 0.5 0.5 1.0 1.0\n")
