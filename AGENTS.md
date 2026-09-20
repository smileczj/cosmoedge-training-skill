# Working on this repository

This repository distributes a training-assistance Skill, not a fixed training recipe.
Preserve the host agent's ability to investigate, choose tools, write code, adapt
the plan and ask useful questions. References are conditional guidance; historical
models, tools, ratios and hyperparameters are not universal requirements.

Keep SKILL.md focused. Add a helper only for demonstrated repeated work or a
deterministic check that materially improves reliability. Do not build a platform
or require every task to pass through a new execution service.

Test observable behavior and actual artifacts. Keep evaluator rubrics separate
from the materials given to an independent evaluation agent. Synthetic fixtures
test reasoning and tooling, not model accuracy or real deployment.

Runtime data, credentials, model weights and private execution logs belong in an
ignored task directory. Public reports must contain only publishable, verified
facts and distinguish current measurements from historical examples.

Run the relevant Python tests and the package/link checks before release. Validate
the installed Skill from a fresh directory, not only the source checkout. User
documentation is Chinese first; explain necessary technical terms in plain words.
