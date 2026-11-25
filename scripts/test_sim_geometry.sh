set -e
source /home/jetson/slam_ws/src/nano_slam/scripts/simulation_env.sh
python - <<'PY'
from __future__ import print_function
import imp,math,os
m=imp.load_source('sim_geometry_under_test',os.path.expanduser('~/slam_ws/src/nano_slam/scripts/sim_base.py'))
s=m.Simulator.__new__(m.Simulator);s.dynamic=False
assert not s.collision(1,1,0)
assert s.collision(.20,1,0)
assert not s.collision(.31,1,0)
assert s.collision(.31,1,math.pi/4)
assert not s.collision(3.5,1,0)
s.dynamic=True
assert s.collision(3.5,1,0)
assert not s.collision(3.32267,1.57643,.12063)
assert s.collision(7.8,1,0)
print('GEOMETRY_TESTS_PASSED: walls, orientation, obstacle insertion, and exact corner clearance')
PY
