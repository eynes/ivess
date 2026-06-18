# Procedures
For updating all the submodules up to last commit:
```
git submodule sync --recursive
git submodule update --init --recursive --remote
git submodule foreach --recursive 'git status --porcelain=v1 && git log -1 --oneline'
```
```
Update all remote
git push origin stage && git push gitlab stage
```
