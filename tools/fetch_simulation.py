"""Fetch actual simulation test results and plot the measured trajectory."""
import getpass
import json
import os
from pathlib import Path
import paramiko
import yaml
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

root=Path(__file__).resolve().parents[1]
output=root/'artifacts'/'simulation';output.mkdir(parents=True,exist_ok=True)
client=paramiko.SSHClient();client.load_host_keys(str(root/'tools'/'known_hosts'))
try:
    client.connect(os.environ.get("JETSON_HOST", "jetson.local"),username='jetson',
                   password=os.environ.get('JETSON_SSH_PASSWORD') or getpass.getpass('SSH password: '),
                   look_for_keys=False,allow_agent=False,timeout=10)
    with client.open_sftp() as sftp:
        for name in ('mapping_report.json','navigation_report.json'):
            sftp.get('/home/jetson/slam_ws/logs/simulation/'+name,str(output/name))
        for ext in ('.pgm','.yaml'):
            sftp.get('/home/jetson/maps/sim_room'+ext,str(output/('sim_room'+ext)))
finally:client.close()
mapping=json.loads((output/'mapping_report.json').read_text())
navigation=json.loads((output/'navigation_report.json').read_text())
assert mapping['passed'] and navigation['passed'], 'The latest acceptance run did not pass'
assert navigation['collisions']==0
metadata=yaml.safe_load((output/'sim_room.yaml').read_text())
image=np.array(Image.open(output/'sim_room.pgm'))
resolution=metadata['resolution'];x0,y0,_=metadata['origin']
trace=np.array(navigation['trace'])
fig,ax=plt.subplots(figsize=(9,7),constrained_layout=True)
ax.imshow(image,cmap='gray',vmin=0,vmax=255,origin='upper',
          extent=[x0,x0+image.shape[1]*resolution,y0,y0+image.shape[0]*resolution])
ax.plot(trace[:,1],trace[:,2],color='#2463a6',linewidth=1.7,label='Combined trajectory of all goal tests')
goals=np.array([g['goal'][:2] for g in navigation['goals']])
ax.scatter(goals[:,0],goals[:,1],marker='x',s=65,color='#b33e2c',label='Navigation goals',zorder=5)
ax.add_patch(Rectangle((2.5,-.4),.6,.8,fill=False,edgecolor='#b33e2c',linestyle='--',linewidth=1.8,label='New obstacle (absent from saved map)'))
ax.set(xlim=(-1.2,7.3),ylim=(-1.2,5.3),xlabel='Map x (m)',ylabel='Map y (m)',
       title='SLAM map and navigation test (2026-11-06)\nIdeal wheel odometry; dashed obstacle present for goal 3 only')
ax.set_aspect('equal');ax.legend(loc='upper left',fontsize=8)
fig.savefig(output/'navigation_preview.png',dpi=150)
summary={
    'simulation_only':True,'mapping_passed':mapping['passed'],
    'navigation_passed':navigation['passed'],'goals_passed':len(navigation['goals']),
    'maximum_true_goal_error_m':max(g['true_position_error_m'] for g in navigation['goals']),
    'maximum_amcl_position_error_m':max(g['amcl_position_error_m'] for g in navigation['goals']),
    'collisions':navigation['collisions'],'dynamic_obstacle_detour_m':navigation['dynamic_obstacle_detour_m'],
    'safety':navigation['safety'],'limitations':['ideal wheel odometry','synthetic 2D laser and environment','no hardware validation']
}
(output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary,indent=2))
print(output/'navigation_preview.png')
