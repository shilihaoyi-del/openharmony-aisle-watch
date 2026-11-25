"""Download the latest real map and make a cropped preview of observed cells."""
import getpass
import os
from pathlib import Path
import paramiko
from PIL import Image, ImageChops

root = Path(__file__).resolve().parents[1]
client = paramiko.SSHClient()
client.load_host_keys(str(root/'tools'/'known_hosts'))
try:
    client.connect(os.environ.get("JETSON_HOST", "jetson.local"), username='jetson',
                   password=os.environ.get('JETSON_SSH_PASSWORD') or getpass.getpass('SSH password: '),
                   look_for_keys=False, allow_agent=False, timeout=10)
    with client.open_sftp() as sftp:
        with sftp.open('/home/jetson/slam_ws/logs/latest_saved_map.txt') as handle:
            remote = handle.read().decode().strip()
        if not remote.startswith('/home/jetson/maps/') or '..' in remote:
            raise ValueError('Unexpected map path')
        output = root/'artifacts'/Path(remote).name
        output.parent.mkdir(exist_ok=True)
        for extension in ('.pgm', '.yaml'):
            sftp.get(remote+extension, str(output.with_suffix(extension)))
    image = Image.open(output.with_suffix('.pgm')).convert('L')
    bounds = ImageChops.difference(image, Image.new('L', image.size, 205)).getbbox()
    if bounds:
        x0,y0,x1,y1 = bounds
        crop = image.crop((max(0,x0-10),max(0,y0-10),min(image.width,x1+10),min(image.height,y1+10)))
        crop.resize((crop.width*4,crop.height*4), Image.Resampling.NEAREST).save(output.with_suffix('.png'))
        print('Observed-cell bounds in full PGM:', bounds)
    print('LOCAL_MAP='+str(output))
finally:
    client.close()
