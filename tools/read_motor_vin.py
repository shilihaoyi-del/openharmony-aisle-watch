"""Read the schematic's PC0 VIN divider via ADC1; no motor output commands."""
import datetime,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CLI='D:/ST-LINK/ST-LINK Utility/ST-LINK_CLI.exe'
SN='34FF74064D56383341362443'

def main():
    folder=ROOT/'artifacts/car_power'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    folder.mkdir(parents=True,exist_ok=False)
    def run(*arguments,allow_self_clear=False):
        args=[CLI,'-c','SN='+SN,'SWD','HOTPLUG','FREQ=100']+list(arguments)
        result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=15)
        out=result.stdout.decode(errors='replace')
        with (folder/'stlink.log').open('a',encoding='utf-8') as handle:handle.write(out+'\n')
        if (result.returncode and not allow_self_clear) or not re.search(r'Device ID:\s*0x414\b',out,re.I):raise RuntimeError('ADC debug access failed')
        return out
    def read(*addresses):
        args=[]
        for address in addresses:args+=['-r32',hex(address),'1']
        out=run(*args);values={}
        for address in addresses:
            match=re.search(r'0x%08x\s*:\s*([0-9a-f]{8})'%address,out,re.I)
            if not match:raise RuntimeError('Missing ADC register')
            values[address]=int(match.group(1),16)
        return values
    def write(pairs,self_clear=False):
        args=[]
        for address,value in pairs:args+=['-w32',hex(address),hex(value)]
        # CLI verifies every write; ADC trigger/calibration bits clear in hardware.
        # Those writes are validated by subsequent ADC status reads instead.
        run(*args,allow_self_clear=self_clear)
    original=read(0x40021018,0x40011000,0x40000400,0x4000040c)
    assert not original[0x40000400]&1 and not original[0x4000040c],'Motor timer must remain stopped'
    assert not original[0x40021018]&0x200,'ADC1 already in use; do not modify it'
    report={'original':{hex(a):v for a,v in original.items()},'motor_commands_sent':False,
            'divider_assumption':'VIN -> 10k -> PC0 -> 1k -> GND; matches both supplied schematics'}
    try:
        write([(0x40021018,original[0x40021018]|0x200),
               (0x40011000,original[0x40011000]&~15),
               (0x40012404,0),(0x4001240c,7),(0x4001242c,0),(0x40012434,10),(0x40012408,0xe0001)])
        write([(0x40012408,0xe0009)],self_clear=True)
        assert not read(0x40012408)[0x40012408]&8
        write([(0x40012408,0xe0005)],self_clear=True)
        assert not read(0x40012408)[0x40012408]&4
        samples=[]
        for _ in range(3):
            write([(0x40012400,0),(0x40012408,0x5e0001)],self_clear=True)
            v=read(0x40012400,0x4001244c)
            assert v[0x40012400]&2,'ADC did not complete a conversion'
            samples.append(v[0x4001244c]&4095)
        write([(0x4001240c,7|(7<<21)),(0x40012434,17),(0x40012408,0x9e0001)])
        write([(0x40012400,0),(0x40012408,0xde0001)],self_clear=True)
        v=read(0x40012400,0x4001244c)
        assert v[0x40012400]&2,'VREFINT conversion incomplete'
        reference=v[0x4001244c]&4095
        report['pc0_adc_samples']=samples;report['vrefint_adc']=reference
        if reference:
            report['estimated_vdda_v']=4095*1.2/reference
            report['estimated_vin_v']=sum(samples)/float(len(samples))/reference*1.2*11
        report['estimated_vin_at_vdda_3_3']=sum(samples)/float(len(samples))/4095*3.3*11
    finally:
        write([(0x40012408,0),(0x40012404,0),(0x4001240c,0),(0x4001242c,0),(0x40012434,0),
               (0x40011000,original[0x40011000]),(0x40021018,original[0x40021018])])
        report['restored']=read(0x40021018,0x40011000,0x40000400,0x4000040c)
        report['restored']={hex(a):v for a,v in report['restored'].items()}
        (folder/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2));print('REPORT='+str(folder/'report.json'))

if __name__=='__main__':main()
