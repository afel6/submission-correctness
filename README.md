# submission-correctness

A Claude skill that checks, before a deadline, that the grader can actually install and run your project, whether
the grader is a person or an AI grading agent. It exists because a course project of ours lost most of its
Correctness marks to two problems nobody saw on the developer's machine:

- the README promised "Python 3.11 or newer", but a pinned `scipy==1.18.1` needs Python 3.12, so `pip install`
  failed for the grader before anything ran;
- the demo needed a trained model that only existed on a private Google Drive.

Both were easy to fix, but they were found after the deadline. This skill finds them before it.

## What it checks

1. **The graded version**: the exact commit the grader will see, tagged once everything passes.
2. **The install promise**: `scripts/check_install.py` asks PyPI whether every pinned package installs on every
   Python version the project promises, on Windows, Linux and macOS, and flags a README that promises an older
   Python than `requires-python`.
3. **A fresh clone**: the README's own commands, copied exactly, on the oldest and newest promised Python, with no
   private files.
4. **CI**: green on the graded commit, on Linux and Windows.
5. **The numbers**: every figure in the README, report and slides traced to its result file (value, split, metric).
6. **The assignment brief**: every required item ticked with evidence.
7. **A mock grade**: a fresh AI agent with no history grades the repo in a clean Docker container, because a
   grader that runs on your machine never meets what a stranger meets.

It also tells you how to make a repo easy for an AI grading agent: one "For graders" path, an `AGENTS.md`, one
verify command and claims it can recompute in seconds. It never suggests writing anything aimed at the grade itself.

## Install

**Claude Code, as a plugin** (recommended):

```text
/plugin marketplace add afel6/submission-correctness
/plugin install submission-correctness@submission-correctness
```

**Claude Code, by hand**: copy `skills/submission-correctness` into your skills folder, so you have
`~/.claude/skills/submission-correctness/SKILL.md` (on Windows `C:\Users\<you>\.claude\skills\...`). It loads in your
next session.

**claude.ai**: download `submission-correctness.skill` from the
[latest release](https://github.com/afel6/submission-correctness/releases/latest) and upload it in
Settings → Capabilities → Skills.

Then just work as usual: the skill starts when you say things like "submit", "final version", "before the deadline"
or "make sure the TA can run it".

## The install check on its own

```bash
pip install packaging
python skills/submission-correctness/scripts/check_install.py path/to/your/project
```

It needs Python 3.11 or newer and network access to PyPI. One row per pinned package, one cell per Python version:
`OK`, `SRC` (source package only: a compiler is needed unless it is pure Python), `NO` or `MISSING` (blockers),
`-` (an environment marker skips it). Exit code 0 means no blockers, 1 at least one, 2 bad input or PyPI unreachable.

Run its tests with `python -m pytest skills/submission-correctness/scripts/test_check_install.py` (no network needed).

## License

MIT
