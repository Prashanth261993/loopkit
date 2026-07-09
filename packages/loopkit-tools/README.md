# loopkit-tools

Shared, **safety-aware** tools for LoopKit agents — the concrete capabilities the
core kernel deliberately does *not* ship. `loopkit` gives you the `ToolRegistry`
mechanism (registration, specs, the dry-run/allow-list safety gate); this package
gives you real handlers to register into it.

Four families, all stdlib-backed (zero third-party deps):

| module            | tools                                   | destructive?         |
|-------------------|-----------------------------------------|----------------------|
| `loopkit_tools.fs`      | `fs.read`, `fs.list`, `fs.write`  | `fs.write` only      |
| `loopkit_tools.process` | `proc.run`                        | yes                  |
| `loopkit_tools.git`     | `git.status`, `git.diff`, `git.commit`, `git.apply` | commit/apply |
| `loopkit_tools.http`    | `http.get`                        | no                   |

Every destructive tool is flagged `destructive=True`, so LoopKit's registry gate
turns it into a **dry-run** unless the caller passes its name in the write
allow-list. Read tools never mutate anything.

```python
from loopkit import ToolRegistry
from loopkit_tools import register_all

reg = ToolRegistry(allow_writes=["fs.write"])   # only fs.write may really write
register_all(reg)
reg.execute("fs.read", {"path": "README.md"})   # runs
reg.execute("proc.run", {"cmd": ["rm", "-rf", "/"]})  # dry-run (not allow-listed)
```
