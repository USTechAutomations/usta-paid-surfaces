You are building '{{SLUG}}' for US Tech Automations. Work in numbered steps. Keep turns under {{MAX_TURNS}}.
Read {{COMMON_PATH}} first and obey it.

WRITE PATHS: {{WRITE_PATHS}}
REPORT_DIR: {{REPORT_DIR}}

GOAL: {{GOAL_ONE_LINER}}

STEPS
{{STEPS}}

FIXTURES
- Known-good (must PASS): {{KNOWN_GOOD_FIXTURE}}
- Known-bad (must FAIL): {{KNOWN_BAD_FIXTURE}}

DONE looks like this command, expected raw exit 0:
{{FINISH_TEST}}

EXTRA WALLS: {{EXTRA_WALLS}}
