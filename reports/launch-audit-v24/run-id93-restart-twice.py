"""Run the isolated account/Studio restart browser check twice consecutively."""
import json,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[2];folder=Path(__file__).resolve().parent
script=folder/"browser-id93-local-process-restart.py";rounds=[]
for number in (1,2):
    run=subprocess.run([sys.executable,str(script)],cwd=root,text=True,capture_output=True,timeout=180)
    if run.returncode:
        print(run.stdout);print(run.stderr,file=sys.stderr);raise SystemExit(run.returncode)
    evidence=json.loads(run.stdout)
    assert evidence["result"]=="passed",evidence
    (folder/f"browser-id93-local-process-restart-round-{number}.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    rounds.append({"round":number,"result":evidence["result"],"same_user_survived":evidence["original_account_id_survived"],"studio_marker_restored":"ID93 RESTART SURVIVAL MARKER" in evidence["after_restart"]["pageText"],"page_errors":evidence["page_errors"]})
aggregate={"runs":rounds,"consecutive_passes":len(rounds)==2 and all(r["result"]=="passed" for r in rounds),"scope":"isolated local data-directory process restarts only; not deployed volume/redeploy proof"}
(folder/"browser-id93-local-process-restart-rounds.json").write_text(json.dumps(aggregate,indent=2),encoding="utf-8")
print(json.dumps(aggregate,indent=2))
