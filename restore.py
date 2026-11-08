# -*- coding: utf-8 -*-
"""Restore MajdataPlay's managed assembly from your own pristine backup.

Only Assembly-CSharp.dll is replaced. Charts, skins, score databases and
settings.json are never touched. This repository ships NO game binaries:
keep your own copy of the original 2.0.3 DLL.

Usage:
    python restore.py "D:\\Games\\MajdataPlay_Build-LATEST"
    python restore.py --dll "C:\\backup\\Assembly-CSharp.dll" "D:\\Games\\..."
"""
import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(TOOL_DIR)
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

ap = argparse.ArgumentParser(description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("game", nargs="?", help="directory containing MajdataPlay.exe")
ap.add_argument("--dll", help="path to your pristine Assembly-CSharp.dll")
args = ap.parse_args()

game_dir = args.game or input("MajdataPlay install directory: ").strip().strip('"')
target = os.path.join(game_dir, "MajdataPlay_Data", "Managed", "Assembly-CSharp.dll")
if not os.path.isfile(target):
    sys.exit("Managed assembly not found: %s" % target)

candidates = [args.dll] if args.dll else [
    os.path.join(PARENT, "original_backup", "Assembly-CSharp.dll"),
    os.path.join(PARENT, "fault_patch_backup", "Assembly-CSharp.dll"),
    os.path.join(TOOL_DIR, "original_backup", "Assembly-CSharp.dll"),
]
source = next((p for p in candidates if p and os.path.isfile(p)), None)
if not source:
    sys.exit("Pristine DLL not found. Pass --dll <path> to your own 2.0.3 original.\n"
             "Searched:\n  " + "\n  ".join(p for p in candidates if p))

if os.name == "nt":
    try:
        p = subprocess.run(["tasklist", "/FI", "IMAGENAME eq MajdataPlay.exe", "/NH"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=20, creationflags=CREATE_NO_WINDOW)
        if "MajdataPlay.exe" in p.stdout:
            sys.exit("MajdataPlay.exe is running. Close the game before restoring.")
    except SystemExit:
        raise
    except Exception:
        pass

backups = os.path.join(TOOL_DIR, "backups")
os.makedirs(backups, exist_ok=True)
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = os.path.join(backups, "Assembly-CSharp_%s.dll" % stamp)
shutil.copy2(target, backup)
shutil.copy2(source, target)
print("current DLL backed up to: %s" % backup)
print("restored from           : %s" % source)
print("DONE - original assembly restored (no other files were touched).")
