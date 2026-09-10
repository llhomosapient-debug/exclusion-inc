# Exclusion Inc

A local-first AI assistant designed to run on-device with no cloud inference.

## Current status

Step 1 is complete: the local shell and security-audit foundation are in place.

- No cloud/API inference
- No normal conversation logging
- Local hash-chained security audit events
- Protected-resource attempt detection
- `#endconvo` exits the session

## Planned next step

Add a local GGUF model through `llama.cpp` and connect it to the shell.

## Privacy

Security events are kept locally by default. Secrets, credentials, model files,
and audit logs are excluded from Git.
