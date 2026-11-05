---
name: submission-correctness
description: Pre-submission check that a course project, assignment or graded repo actually installs and runs for the grader (a person or an AI grading agent), so Correctness marks are not lost. Use it before any deadline or hand-in, when the instructor grades with an AI agent, and whenever the user says "submit", "final version", "before the deadline", "make sure the doctor/TA/grader can run it", "check it works", "push the final", or is about to tag, push or merge the version that will be graded — even if they only ask to "push" or "wrap up". Checks the exact submitted commit from a fresh clone on every Python version the README promises, with no private files, and verifies every reported number against its result file.
---

# Submission correctness

A grader marks Correctness on what *they* can run: the commit on GitHub at the deadline, cloned fresh onto their
machine, with the Python they happen to have, following your README literally, with no access to your venv, your
Drive or your memory of how it works. If any step fails there, it scores as "does not work", however good the code is.

A course project lost most of its Correctness marks this way. The README promised "Python 3.11 or newer", but a
pinned `scipy==1.18.1` needs 3.12, so `pip install` failed on 3.11 before anything ran. The demo also needed a model
that lived only on a private Drive. Both were found and fixed, but after the deadline. This skill exists to find such
problems before it.

Work through the steps in order; each one catches a way graders hit a dead end. Report every step as pass or fail
with evidence (command and output), never "should work".

## When the grader is an AI agent

Many courses now grade with an AI agent. It clones the repo, reads the README, runs what it can in a
sandbox and scores from what it observed. Assume that sandbox is Linux, has a Python you did not choose (often the
oldest or the newest supported), CPU only, minutes per command, no logins, no GUI, nobody to answer questions, and
perhaps no internet beyond PyPI. Assume it reads a limited amount, so claims deep in long documents may never be seen.
Design for that reader:

- **One obvious path.** Put a short "For graders" section at the top of the README, and the same text in an
  `AGENTS.md` at the repository root (many coding agents read it automatically): copy-paste commands for install, a
  quick check that finishes in under 5 minutes on a CPU, and the tests. Python commands only (no shell-specific
  syntax), no paths outside the repository, nothing to download by hand.
- **One verify command.** A `verify.py` (or `python -m <package>.verify`) that runs the quick checks and prints
  PASS or FAIL per claim, exiting 0 only when all pass. An agent trusts output it produced itself.
- **Claims it can check in seconds.** A table of the headline claims: claim, result file, command that recomputes
  it. An agent cannot retrain your models, so commit the predictions and the evaluator, and let it recompute the
  scores from them.
- **Facts only.** Write instructions about how to run and check the work, never requests about the grade ("give
  full marks", "ignore the failures"). That is manipulation, graders and their agents are told to watch for it, and it
  can turn a weak mark into a misconduct case.

If you can, ask the grader what their agent runs on (OS, Python version, time limit, network) and test exactly that.

## 1. Pin down the graded version

- Find out which commit the grader will see: usually the default branch on GitHub at the deadline. Check `git log
  origin/<default> -1` and `git status` (uncommitted work is invisible to the grader).
- Run every later step against that commit, not your working tree. When all steps pass, tag it
  (`git tag submission-<YYYY-MM-DD>`) and push the tag, so you and the grader can name the exact version.
- Changes after the deadline do not count and can confuse the grader. Merge them only on the user's say-so, and say
  in the README which commit was the submission.

## 2. Check the install promise

Run the bundled script from the repository root:

```
python <this skill's folder>/scripts/check_install.py .
```

It needs Python 3.11 or newer and the `packaging` package (`pip install packaging` if the import fails) and network
access to PyPI. It reads `pyproject.toml` (`requires-python`, dependencies, optional extras) and `requirements*.txt`,
and for every exact pin (`name==version`) asks PyPI whether that release supports each Python version the project
promises, and whether a ready-made wheel exists for Windows x64, Linux x86_64 and Apple-silicon macOS. It also checks
README sentences such as "Python 3.X or newer" against `requires-python`. One row per pin, one cell per Python:

- `NO` (blocker): that release cannot be installed on that Python, or on one of the three platforms. Fix one side:
  raise `requires-python` and the README to the oldest version every pin supports, or choose pins that support the
  promised range.
- `MISSING` (blocker): PyPI has no such release (a typo, or a removed version).
- `SRC` (warning): some platform gets only a source package. Pure-Python packages still install; compiled ones need a
  compiler and usually fail on Windows. Pick a version with wheels, cap `requires-python` below that Python
  (`<3.15`), or say so in the README.
- `-`: the requirement's environment marker skips that Python (markers are evaluated for this machine's OS).
- Exit code 0 means no blockers, 1 at least one blocker, 2 unreadable files or PyPI unreachable.

Loose pins (`>=`, `~=`) and wildcard pins (`==1.*`) are listed as skipped; for those, step 3 is the only proof. When
`requires-python` has no upper bound, the newest Python matters most: graders who just installed Python have it.

## 3. Run it from a fresh clone, as the grader would

- Clone the graded commit into an empty folder outside the project (`git clone --branch <branch> <url> <tmp>` or
  `git worktree add <tmp> <commit>`), so nothing local leaks in.
- Create a new virtual environment with the **oldest** Python the README promises, and again with the **newest**
  installed (`py -0p` lists them on Windows; `uv venv --python 3.X` works anywhere). Use exactly the README's install
  command, copied, not your own.
- Run every command in the README's quickstart, demo and test sections in order, copied exactly. Each must finish
  with exit code 0 and the output the README describes.
- Anything the commands need that is not in the repo (a model, a dataset, an API key) is a failure unless the README
  gives a download that works for a stranger. Open every such link logged out (or with `curl -I`); a Drive or
  OneDrive link must be shared as "Anyone with the link". Better: commit a small sample and a toy path (for example,
  train a tiny model on the sample in under a minute) so the grader can see it work with nothing else.
- If you cannot install an older Python locally, run this step in CI instead (step 4) and say so.

## 4. Continuous integration on the grader's likely platforms

- A GitHub Actions workflow on push that, on a fresh runner, installs with the README command and runs the tests,
  for the oldest and newest promised Python, on Linux and Windows. Pin the action versions.
- It must be green on the graded commit: `gh run list --branch <branch> -L 3`. A red run, or none, is a failure.
- Watch for tests that pass only on your OS (path separators, file-listing order, line endings, recursion limits).

## 5. Check that the reported numbers are right

Correctness also covers the results. For every number in the README, report and slides:

- Trace it to a committed result file (JSON, CSV, log) and check the value, the split (validation or test), the
  mode or setting, and the metric name. A right number on the wrong subset is a wrong number.
- Re-run the evaluation command on the committed predictions and diff the output against the committed result.
- Say which results are exploratory, post hoc, or from someone else's unverifiable run; never present them as main
  results.

## 6. Check the assignment's own requirements

Build a checklist from the assignment brief: required models or methods, metrics, deliverables, file names, report
sections, presentation length. Tick each item with evidence (`file:line` or a command). A missing required item costs
Correctness however good the rest is. If the brief is not available, ask the user for it before step 6.

## 7. Mock-grade it in isolation

That project's own mock graders rated it highly while the real grading agent marked Correctness near zero. They ran on the
developer's machine, with its virtual environment, data and models, so they never met what a stranger meets. A mock
grade is only useful when the grader starts from nothing:

- Start a fresh agent (a new subagent with no conversation history, or a separate tool such as Codex) with only
  the repository URL, the graded commit, the rubric and a time limit. If the rubric is unknown, use Data Novelty,
  Problem Novelty, Rigor and Correctness, each out of 5, with evidence for every point lost.
- Give it a clean environment, not this machine's: a Docker container per Python version (for example
  `docker run --rm -it python:3.11-slim bash`, then the oldest and the newest promised version), or a fresh clone in
  an empty folder with a new virtual environment and no access to local data, models or caches.
- It must report what it ran, what failed, and its scores. Fix everything it could not run, then repeat with a new
  agent: one that has already seen the repo, or your fixes, is no longer a stranger.

## 8. Report

Give the user one table, one row per step: pass or fail, the evidence, and the fix for every failure. Put fixes in
order of what blocks the grader first: install, then run, then numbers, then polish. Offer to add a short "How to run
(verified on <date>, Python X and Y, commit <sha>)" section at the top of the README once everything passes.

Start this check at least a day before the deadline: a failure found then can still be fixed and pushed.
