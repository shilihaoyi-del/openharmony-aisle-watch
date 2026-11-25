"""Add the contact node to a dedicated HiSpark OpenHarmony 5.1 checkout."""
import argparse
from pathlib import Path
import shutil


def insert_once(source, anchor, replacement):
    if replacement in source:
        return source
    if source.count(anchor) != 1:
        raise ValueError("Unexpected SDK layout around {!r}".format(anchor))
    return source.replace(anchor, replacement, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sdk", type=Path)
    parser.add_argument("variant", choices=("contact", "fusion", "receiver"), nargs="?", default="contact")
    args = parser.parse_args()
    sdk = args.sdk.resolve(strict=True)
    if not (sdk / "vendor/hihope/nearlink_dk_3863/config.json").is_file():
        parser.error("SDK must contain the nearlink_dk_3863 OpenHarmony mini product")
    application = sdk / "applications/sample/wifi-iot/app"
    platform = sdk / "device/soc/hisilicon/ws63v100/sdk"
    root_gn = application / "BUILD.gn"
    target = platform / "build/config/target_config/ws63/config.py"
    link = platform / "libs_url/ws63/cmake/ohos.cmake"
    files = [
        (root_gn, 'features = [ "startup" ]',
         'features = [ "startup", "ws63_contact_node:ws63_contact_node" ]'),
        (target, '            "hal_iothardware",',
         '            "hal_iothardware",\n            "ws63_contact_node",'),
        (link, '"hal_iothardware" "wifiservice"',
         '"hal_iothardware" "wifiservice" "ws63_contact_node"'),
    ]
    updates = [(path, insert_once(path.read_text(encoding="utf-8"), anchor, replacement))
               for path, anchor, replacement in files]
    target_dir = application / "ws63_contact_node"
    target_dir.mkdir(exist_ok=True)
    for name in ("BUILD.gn", "contact_node.c", "fusion.h", "fusion.c", "fusion_node.c",
                 "fusion_sle.h", "fusion_sle.c", "fusion_receiver.c", "change_watch.h", "change_watch.c"):
        shutil.copyfile(Path(__file__).with_name(name), target_dir / name)
    (target_dir / "fusion_config.gni").write_text(
        'ws63_variant = "{}"\n'.format(args.variant), encoding="utf-8")
    for path, data in updates:
        path.write_text(data, encoding="utf-8")


if __name__ == "__main__":
    main()
