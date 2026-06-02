# GitHub Workflow Guide (PyPSA-Isolated)

This document explains how to install and sync this project using Git and GitHub.

## 1. Clone the repository

```bash
git clone https://github.com/VicenteSF-git/PyPSA-Isolated.git
cd PyPSA-Isolated
```

## 2. Create and activate the Python environment

Recommended (Conda):

```bash
conda env create -f environment.yml
conda activate pypsa-isolated
```

If you later change the dependency file, refresh the environment with:

```bash
conda env update -f environment.yml --prune
```

Optional (if you have a Gurobi license):

```bash
conda install -c gurobi gurobi -y
```

The repository now includes `environment.yml`, so cloning from GitHub and running the commands above is enough to recreate the environment on another machine.

## 3. Run the model from the model/ folder

The model source files now live in the model directory.

```bash
cd model
python -c "import config; print('config import OK')"
```

If import works, your environment is ready.

## 4. Daily update workflow (download latest changes)

From repository root:

```bash
git pull origin main
```

If you have local modifications, commit or stash first:

```bash
git add -A
git commit -m "WIP: local checkpoint"
# or, alternatively:
git stash
git pull origin main
git stash pop
```

## 5. Daily contribution workflow (upload your changes)

From repository root:

```bash
git status
git add -A
git commit -m "Describe your change clearly"
git push origin main
```

If you do not want to stage everything, you can stage specific files:

```bash
git add model/config.py
git add README_github.md model/build_demand.py
git commit -m "Commit only selected files"
git push origin main
```

You can also stage only parts of a file (interactive mode):

```bash
git add -p model/config.py
```

Always verify what is staged before committing:

```bash
git status
git diff --staged
```

## 6. Recommended branch-based workflow

Instead of committing directly to main:

```bash
git checkout -b feature/my-change
# work, then:
git add -A
git commit -m "Implement my change"
git push -u origin feature/my-change
```

Then open a Pull Request on GitHub from feature/my-change to main.

## 7. How to handle push rejection

If push fails with "non-fast-forward", your local branch is behind remote.

```bash
git pull --rebase origin main
git push origin main
```

If conflicts appear:

1. Edit conflicted files and resolve markers.
2. Stage resolved files.
3. Continue rebase.

```bash
git add -A
git rebase --continue
git push origin main
```

## 8. Useful status and history commands

```bash
git status
git log --oneline -n 10
git diff
git diff --staged
```

## 9. Keep generated outputs out of commits

This repository is configured to ignore typical generated artifacts (outputs, caches, local files).

Before pushing, always check:

```bash
git status --short
```

If something should not be tracked, add it to .gitignore before committing.

## 10. First-time Git identity setup (one-time per machine)

```bash
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

## 11. Quick troubleshooting

- Authentication error when pushing:
  - Re-login to GitHub in VS Code or refresh credentials.
- Detached HEAD:
  - Checkout main and pull again.
- Wrong branch:
  - Use `git branch --show-current` and switch with `git checkout <branch>`.

## 12. Minimal safe routine

Use this every time before and after coding:

```bash
# Before coding
git pull origin main

# After coding
git add -A
git commit -m "Short, meaningful message"
git push origin main
```
