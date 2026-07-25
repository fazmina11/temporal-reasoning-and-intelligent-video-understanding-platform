import subprocess
import os

repo_root = os.path.dirname(os.path.abspath(__file__))
repo_url = "https://github.com/fazmina11/temporal-reasoning-and-intelligent-video-understanding-platform.git"

def run_cmd(cmd):
    print(f"==> Executing: {cmd}")
    res = subprocess.run(cmd, cwd=repo_root, shell=True, capture_output=True, text=True)
    if res.stdout:
        print(res.stdout)
    if res.stderr:
        print(res.stderr)
    return res

if __name__ == "__main__":
    print("Preparing repository commit and push...")
    run_cmd("git init")
    run_cmd("git remote remove origin")
    run_cmd(f"git remote add origin {repo_url}")
    run_cmd("git branch -M main")
    run_cmd("git add .")
    run_cmd('git commit -m "Complete VideoSceneRAG frontend and backend integration (Phases 1-14)"')
    print("Pushing to main branch...")
    res = run_cmd("git push -u origin main --force")
    if res.returncode == 0:
        print("\nSuccessfully pushed complete project to GitHub main branch!")
    else:
        print("\nExecution complete. Check output above.")
