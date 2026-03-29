# AGENTS.md

## General Instructions
### Rules
- Any explicit instruction given in a message to overwrite a rule here must be respected.
- Run linters and formatters after writing code.
- If you can't fix a lint issue write it in the `AGENT_NOTES.md`.
- Use semantic versioning and increase the version number whenever you make changes:
  - `<major>.<minor>.<patch>`
  - Simple fixes get a patch increase.
  - Feature implementations get a minor increase.
  - Backward incompatible / breaking changes get a major increase.
  - Explicitly being told to increase the major after implementing a new feature increases the major.
- All the files below must be available in all projects. Use all caps for the filenames (not the extensions).
- Create a link `agents.md` to `AGENTS.md` to support different implementations but keep the same file.

### Files
- `AGENT_NOTES.md` - Keep clear and concise memory of lessons learned and persistent context.
- `BACKLOG.md` - List of future improvements; always append to it while implementing features/fixes.
- `CHANGELOG.md` - List all changes with versioning and GMT+3 timestamp.
- `DESIGN.md` - Store design-related information.
- `README.md`

## Instructions for Web Apps
- Use playwright / selenium to test each UI.
- All assets must be included in the repo for immediate no-network setup.

### Flask Module Organization
```
app/
<module_1>/
<module_2>/
...
static/<module_1>/ # only for custom css and js
static/<module_2>/ # only for custom css and js
templates/<module_1>/
templates/<module_2>/

static/vendors/<vendor_name>/ # for third party libraries
```

## Instructions for AI training
- Display graphs for training loss, performance and other related information very verbosely.
