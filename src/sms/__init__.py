"""School Management System backend — see README.md for what this project
actually is. Deliberately not re-exporting `app`/`create_app` here: main.py
builds the full app (including configure_logging()) as a module-level side
effect, and importing that at the top-level package would trigger it for
any unrelated import of anything under sms.* (e.g. the bootstrap script
importing sms.domains.users.models)."""
