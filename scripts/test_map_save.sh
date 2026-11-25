set -e
source /home/jetson/slam_ws/src/nano_slam/scripts/env.sh
python - <<'PY'
from __future__ import print_function
import math, os, shutil, subprocess, sys, tempfile
import rospy
from nav_msgs.msg import OccupancyGrid
rospy.init_node('nano_map_save_verification', anonymous=True)
topic = '/nano_slam_verification/map'
publisher = rospy.Publisher(topic, OccupancyGrid, queue_size=1, latch=True)
grid = OccupancyGrid()
grid.header.frame_id = 'test_map'
grid.info.width, grid.info.height = 3, 2
grid.info.resolution = 0.05
grid.info.origin.position.x, grid.info.origin.position.y = -1.5, 2.0
grid.info.origin.orientation.z = math.sin(0.3)
grid.info.origin.orientation.w = math.cos(0.3)
grid.data = [0, 100, -1, 100, 0, -1]
folder = tempfile.mkdtemp(prefix='nano-map-save-test-')
try:
    publisher.publish(grid)
    base = os.path.join(folder, 'fixture')
    cmd = [sys.executable, os.path.expanduser('~/slam_ws/src/nano_slam/scripts/save_map.py'), base, '--topic', topic]
    subprocess.check_call(cmd)
    with open(base+'.pgm', 'rb') as handle:
        actual = handle.read()
    expected = b'P5\n3 2\n255\n' + bytes(bytearray([0,254,205,254,0,205]))
    assert actual == expected, repr(actual)
    import yaml
    with open(base+'.yaml') as handle:
        metadata = yaml.safe_load(handle)
    assert metadata['image'] == 'fixture.pgm'
    assert abs(metadata['resolution']-0.05) < 1e-7
    assert abs(metadata['origin'][2]-0.6) < 1e-7
    assert metadata['origin'][:2] == [-1.5,2.0]
    assert subprocess.call(cmd) != 0, 'Must refuse overwriting a saved map'
    grid.data = [-1]*6
    publisher.publish(grid)
    cmd[2] = os.path.join(folder, 'empty')
    assert subprocess.call(cmd) != 0, 'Must reject unobserved maps'
    assert not os.path.exists(cmd[2]+'.pgm')
    print('PASS: map pixel orientation, occupied/free/unknown, resolution, origin/yaw, overwrite protection, empty-map rejection')
finally:
    shutil.rmtree(folder)
PY
echo 'LIVE SENSOR CHECK'
python "$NANO_SLAM_DIR/scripts/check_scan.py" || true
