"""Build the installed app with the catalogue ZIP packaged into its resources."""
import argparse,json,shutil,subprocess,sys,tempfile,zipfile
from pathlib import Path

def main():
    root=Path(__file__).parent
    p=argparse.ArgumentParser();p.add_argument('--catalogue',type=Path,default=Path('D:/Naraka Models/export/naraka-catalogue.zip'));p.add_argument('--output',type=Path,default=root.parent/'NarakaAtelier-install');a=p.parse_args()
    with zipfile.ZipFile(a.catalogue) as z:
        data=z.read('naraka-catalogue/data.js').decode('utf8').strip();prefix='window.CATALOG = '
        if not data.startswith(prefix):raise ValueError('Unsupported catalogue format')
        cat=json.loads(data[len(prefix):-1]);manifest=json.loads((root/'resources/build.json').read_text(encoding='utf8'))
        if cat['gameVersion']['clientVersion']!=manifest['catalogue_version']:raise ValueError('Catalogue build does not match packaged native adapters')
    packaged=root/'resources/catalogue.zip'
    if a.catalogue.resolve()!=packaged.resolve():shutil.copyfile(a.catalogue,packaged)
    cmd=[sys.executable,'-m','PyInstaller','--noconfirm','--onedir','--noconsole','--name','NarakaAtelier','--distpath',str(a.output),'--workpath',str(root.parent/'work/app-pyinstaller'),'--specpath',str(root),'--paths',str(root/'vendor'),'--collect-all','UnityPy','--collect-all','lz4']
    for mod in ['pandas','scipy','matplotlib','torch','sklearn','IPython','pytest','playwright']:cmd+=['--exclude-module',mod]
    for name in ('resources','web','vendor'):cmd+=['--add-data',str(root/name)+';'+name]
    cmd.append(str(root/'main.py'));subprocess.run(cmd,check=True)

if __name__=='__main__':main()
