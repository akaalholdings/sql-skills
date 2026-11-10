# Advisory lesson recall

Detail for `SKILL.md`. Its boundaries apply here; nothing in this file relaxes them.

After the gate passes and the review has returned, you may call
`recall_lessons` with exactly these fields:

`recall_lessons(skill=sql-index-manager, skill_version=2.1.0,
runtime_compatibility_fingerprint=<stable>, tool_schema_fingerprint=<stable>,
sanitized_config_fingerprint=<stable>, database_name=<selected>, tags=<supported>)`

Never send raw SQL, credentials, index names, parameter values, rows, or hidden
reasoning. Do not pass the process `runtime_fingerprint`.
