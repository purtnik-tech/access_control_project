import xml.etree.ElementTree as ET
from pathlib import Path
from PIL import Image

DATASET_DIR = "C:\\license_plates_car_dataset"

IMG_DIR = Path(DATASET_DIR) / "images"
ANN_DIR = Path(DATASET_DIR) / "annotations"
OUT_DIR = Path(DATASET_DIR) / "labels"

OUT_DIR.mkdir(parents=True, exist_ok=True)


def convert_bbox(img_w, img_h, xmin, ymin, xmax, ymax):
    x_center = (xmin + xmax) / 2 / img_w
    y_center = (ymin + ymax) / 2 / img_h
    w = (xmax - xmin) / img_w
    h = (ymax - ymin) / img_h
    return x_center, y_center, w, h


def parse_xml(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    size = root.find("size")
    img_w = int(size.find("width").text)
    img_h = int(size.find("height").text)

    objects = []

    for obj in root.findall("object"):
        cls = obj.find("name").text

        bndbox = obj.find("bndbox")
        xmin = int(bndbox.find("xmin").text)
        ymin = int(bndbox.find("ymin").text)
        xmax = int(bndbox.find("xmax").text)
        ymax = int(bndbox.find("ymax").text)

        objects.append((cls, xmin, ymin, xmax, ymax))

    return img_w, img_h, objects


def class_map(label):
    # YOLO требует int class_id
    # у тебя пока один класс: license plate
    return 0


for xml_file in ANN_DIR.glob("*.xml"):
    img_name = xml_file.stem + ".png"
    img_path = IMG_DIR / img_name

    if not img_path.exists():
        img_name = xml_file.stem + ".jpg"
        img_path = IMG_DIR / img_name

    if not img_path.exists():
        print(f"[SKIP] image not found for {xml_file.name}")
        continue

    img = Image.open(img_path)
    img_w, img_h = img.size

    _, _, objects = parse_xml(xml_file)

    label_path = OUT_DIR / f"{xml_file.stem}.txt"

    with open(label_path, "w") as f:
        for cls, xmin, ymin, xmax, ymax in objects:

            x, y, w, h = convert_bbox(img_w, img_h, xmin, ymin, xmax, ymax)

            # фильтрация мусора
            if w <= 0 or h <= 0:
                continue

            cls_id = class_map(cls)

            f.write(f"{cls_id} {x:.6f} {y:.6f} {w:.6f} {h:.6f}\n")
