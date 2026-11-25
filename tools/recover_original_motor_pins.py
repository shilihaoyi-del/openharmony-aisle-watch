"""Reproduce the pin-table evidence from the original target flash backup."""
import hashlib
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'artifacts/stlink_backup/20261122-172929/original_flash_08000000_256k.bin'
data=source.read_bytes()
digest=hashlib.sha256(data).hexdigest()
assert digest=='469fff7a9f38bc74a030c56dbed6f1bb59e8b7292792e165ddffcfe1858f3d6c'
assert struct.unpack_from('<3I',data,0x63e0)==(0x08006404,0x20000000,0xc0)
# Thumb STR R1,[R0,#0x14]; BX LR; STR R1,[R0,#0x10]; BX LR.
assert data[0x13dc:0x13e4]==bytes.fromhex('4161704701617047')
ports=struct.unpack_from('<4I',data,0x6448)
pwm_ports=struct.unpack_from('<4I',data,0x6458)
set_for_original_positive=struct.unpack_from('<4H',data,0x5fc4)
reset_for_original_positive=struct.unpack_from('<4H',data,0x5fcc)
pwm_pins=struct.unpack_from('<4H',data,0x5fd4)
timers=struct.unpack_from('<4I',data,0x6468)
assert timers==(0x40000400,)*4
names={0x40010800:'PA',0x40010c00:'PB',0x40011000:'PC'}
def pin(port,mask):
    assert mask and not mask&(mask-1)
    return names[port]+str(mask.bit_length()-1)
report={'source':str(source),'sha256':digest,'spin_function':'0x08003228',
        'gpio_reset_function':'0x080013dc','gpio_set_function':'0x080013e0',
        'port_tables_flash':['0x08006448','0x08006458'],
        'pin_tables_flash':['0x08005fc4','0x08005fcc','0x08005fd4'],
        'note':'Bench positive uses the opposite direction to the original spin-positive, retaining the already-tested M1/M2 bench sign.',
        'motors':[]}
for i in range(4):
    report['motors'].append({'motor':i+1,
        'original_spin_positive_high':pin(ports[i],set_for_original_positive[i]),
        'original_spin_positive_low':pin(ports[i],reset_for_original_positive[i]),
        'bench_positive_high':pin(ports[i],reset_for_original_positive[i]),
        'bench_positive_low':pin(ports[i],set_for_original_positive[i]),
        'pwm':pin(pwm_ports[i],pwm_pins[i]),'timer':'TIM3','channel':i+1})
target=ROOT/'artifacts/car_diagnosis/original_motor_pins.json'
target.write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
