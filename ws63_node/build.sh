#!/usr/bin/env bash
set -euo pipefail

source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
sdk=$(cd -- "${1:?path to the dedicated OpenHarmony SDK checkout}" && pwd)
cd -- "$sdk"
python3 "$source_dir/install_into_sdk.py" "$sdk" "${2:-contact}"
# The SDK's archiver updates existing archives without removing obsolete members.
rm -f -- "$sdk/out/nearlink_dk_3863/nearlink_dk_3863/libs/libws63_contact_node.a"
export PATH="$sdk/device/soc/hisilicon/ws63v100/sdk/tools/bin/compiler/riscv/cc_riscv32_musl_100/cc_riscv32_musl/bin:$sdk/prebuilts/build-tools/linux-x86/bin:$PATH"
if [[ -x "$sdk/.hb-deps/bin/hb" ]]; then
    export PYTHONPATH="$sdk/.hb-deps${PYTHONPATH:+:$PYTHONPATH}"
    hb_cmd="$sdk/.hb-deps/bin/hb"
else
    hb_cmd=hb
fi
"$hb_cmd" set -p nearlink_dk_3863
"$hb_cmd" build -f
