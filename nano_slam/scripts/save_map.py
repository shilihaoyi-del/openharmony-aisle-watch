#!/usr/bin/env python
"""Save a real /map to PGM/YAML without requiring the map_server package."""
from __future__ import print_function
import argparse
import json
import math
import os
import sys
import rospy
from nav_msgs.msg import OccupancyGrid

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', nargs='?', default=os.path.expanduser('~/maps/room'))
    parser.add_argument('--topic', default='/map')
    args = parser.parse_args(rospy.myargv()[1:])
    rospy.init_node('nano_save_map', anonymous=True)
    grid = rospy.wait_for_message(args.topic, OccupancyGrid, timeout=15)
    width, height = grid.info.width, grid.info.height
    known = sum(1 for value in grid.data if value >= 0)
    if not width or not height or len(grid.data) != width * height or not known:
        raise ValueError('Map has no observed cells; connect the lidar and scan first')
    base = os.path.abspath(os.path.expanduser(args.output))
    if os.path.exists(base+'.pgm') or os.path.exists(base+'.yaml'):
        raise ValueError('Output already exists; choose a new map name')
    parent = os.path.dirname(base)
    if not os.path.isdir(parent):
        os.makedirs(parent)
    # Same trinary conversion as the traditional ROS map_saver.
    pixels = bytearray(0 if value >= 65 else 254 if 0 <= value <= 25 else 205
                       for y in range(height-1, -1, -1)
                       for value in grid.data[y*width:(y+1)*width])
    q = grid.info.origin.orientation
    yaw = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
    p = grid.info.origin.position
    with open(base+'.pgm', 'wb') as handle:
        handle.write(('P5\n{} {}\n255\n'.format(width, height)).encode('ascii'))
        handle.write(pixels)
    with open(base+'.yaml', 'w') as handle:
        handle.write('image: {}\nresolution: {}\norigin: [{}, {}, {}]\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.196\n'.format(
            json.dumps(os.path.basename(base)+'.pgm'), grid.info.resolution, p.x, p.y, yaw))
    print('MAP_SAVED {}.pgm + .yaml; {}x{}, observed_cells={}'.format(base, width, height, known))

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('MAP_SAVE_FAILED: {}'.format(exc), file=sys.stderr)
        sys.exit(1)
