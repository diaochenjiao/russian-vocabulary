from pathlib import Path
import shutil
root=Path(__file__).resolve().parent
source=root/'seed-data';target=root/'data';target.mkdir(exist_ok=True)
for f in source.iterdir():
 if f.is_file() and not (target/f.name).exists():shutil.copy2(f,target/f.name)
