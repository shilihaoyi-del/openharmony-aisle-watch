set -e
project="$(cd "$(dirname "$0")/.." && pwd)"
root="$project/nano_slam"
build="$project/artifacts/protocol_tests_linux"
mkdir -p "$build"
g++ -std=c++11 -Wall -Wextra -Werror -pedantic \
  -I "$root/firmware/j1_protocol_demo" \
  "$root/firmware/j1_protocol_demo/j1_protocol.cpp" \
  "$root/tests/protocol_board_tests.cpp" -o "$build/protocol_board_tests"
"$build/protocol_board_tests"
export J1_BOARD_EMULATOR="$build/protocol_board_tests"
python3 -m unittest discover -s "$root/tests" -p test_motor_protocol.py -v
