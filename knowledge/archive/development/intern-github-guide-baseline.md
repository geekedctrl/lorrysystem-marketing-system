> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

You should **not edit the live server directly**.

## First Time Setup

Install:

- Git
- VS Code

Accept the GitHub repository invitation.

Repository:
```text
https://github.com/geekedctrl/lorrysystem-marketing-system
```

## Download the Project

Open PowerShell, Command Prompt, or the VS Code terminal:
```bash
git clone https://github.com/geekedctrl/lorrysystem-marketing-system.git
cd lorrysystem-marketing-system
code .
```

You only need to clone the repository once.

## Before Starting a New Task

Always start from the latest `develop` branch:

```bash
git switch develop
git pull
```

Then create your own branch:

```bash
git switch -c feature/task-name
```

Example:

```bash
git switch -c feature/research-worker
```

## Do Your Coding

Make your changes normally in VS Code.

Do not work directly on:

```text
main
develop
```

Always work inside your own `feature/*` branch.

## When You Finish

Check your changes:

```bash
git status
```

Prepare them:

```bash
git add .
```

Save them into Git:

```bash
git commit -m "describe what you changed"
```

Example:

```bash
git commit -m "feat: improve research worker"
```

Push your branch:

```bash
git push
```

If Git tells you to set an upstream branch, copy and run the command it gives you.

It may look like:

```bash
git push --set-upstream origin feature/research-worker
```

# IMPORTANT: STOP HERE

After the branch has been pushed:

**Do not create a Pull Request.**

**Do not merge anything.**

**Do not push directly to `develop`.**

**Do not push directly to `main`.**

Send the branch name to the project owner and wait for further instructions.

Example message:

```text
I have finished the task and pushed my branch.

Branch:
feature/research-worker
```

The project owner will review the branch first.

Only create a Pull Request if the project owner specifically tells you to do so.

## If Changes Are Requested

Stay on the same feature branch.

Make the requested changes, then run:

```bash
git add .
git commit -m "fix: update requested changes"
git push
```

Then inform the project owner again.

## Starting the Next Task

For every new task:

```bash
git switch develop
git pull
git switch -c feature/new-task-name
```

Do not reuse an old feature branch.

## Important Rules

Never work directly on:

```text
main
develop
```

Never upload:

```text
.env files
passwords
API keys
database files
private keys
credentials
```

Never edit production directly.

Never create or merge a Pull Request unless instructed.

## The Whole Process

```text
Latest develop
      ↓
Create feature branch
      ↓
Code in VS Code
      ↓
Commit changes
      ↓
Push feature branch
      ↓
STOP
      ↓
Tell project owner
      ↓
Wait for instruction
```

The most important rule is:

```text
Push your feature branch, then stop and wait.
Do not create or merge a Pull Request unless told to.
```