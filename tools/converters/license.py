import json
from pathlib import Path


DATASET_ROOT = Path("C:\\license_plates_dataset")


def build_annotation_file(split: str):
    split_dir = DATASET_ROOT / split

    ann_dir = split_dir / "ann"
    img_dir = split_dir / "img"

    output_file = DATASET_ROOT / f"{split}.txt"

    rows = []

    for json_file in ann_dir.glob("*.json"):
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        plate_text = data.get("description")

        if not plate_text:
            continue

        image_file = img_dir / f"{json_file.stem}.png"

        if not image_file.exists():
            print(f"Missing image: {image_file}")
            continue

        abs_path = image_file.resolve()

        rows.append(f"{abs_path}\t{plate_text}")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(rows))

    print(f"{split}: {len(rows)} samples")


for split in ["train", "val", "test"]:
    build_annotation_file(split)
