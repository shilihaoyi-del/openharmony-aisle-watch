set -e
root=/home/jetson/slam_ws/src/nano_slam
build=/home/jetson/slam_ws/logs/protocol_tests
mkdir -p "$build"
g++ -std=c++11 -Wall -Wextra -Werror -pedantic \
  -I "$root/firmware/j1_protocol_demo" \
  "$root/tests/four_wheel_pwm_tests.cpp" -o "$build/four_wheel_pwm_tests"
"$build/four_wheel_pwm_tests"
g++ -std=c++11 -Wall -Wextra -Werror -pedantic \
  -I "$root/firmware/j1_protocol_demo" \
  "$root/firmware/j1_protocol_demo/j1_protocol.cpp" \
  "$root/tests/protocol_board_tests.cpp" -o "$build/protocol_board_tests"
"$build/protocol_board_tests"
export J1_BOARD_EMULATOR="$build/protocol_board_tests"
python -m unittest discover -s "$root/tests" -p test_motor_protocol.py -v
python3 -m unittest discover -s "$root/tests" -p test_motor_protocol.py -v
python "$root/scripts/motor_link.py" jog --axis 0 --steps 50 --rate 100
