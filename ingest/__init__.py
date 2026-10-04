"""Optional source adapters that feed the common {event, context, question} case schema.

Nothing in the core benchmark imports this package. Each adapter is toggled by
its own config file so that disabling it removes its suite without touching core
code (docs/PRACTICAL_EVAL_V2.md section 3a).
"""
