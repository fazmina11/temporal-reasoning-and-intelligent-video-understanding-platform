@echo off
echo Preparing git commit and push to GitHub...
git init
git remote remove origin 2>nul
git remote add origin https://github.com/fazmina11/temporal-reasoning-and-intelligent-video-understanding-platform.git
git branch -M main
git add .
git commit -m "Complete VideoSceneRAG frontend and backend integration (Phases 1-14)"
git push -u origin main
echo Done!
