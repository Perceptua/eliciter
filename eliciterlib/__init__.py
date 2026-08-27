"""eliciter — ask for writing, based on what you have been reading and writing.

Import order matters exactly once: `config.bootstrap()` must run before anything that
touches `notelib` or `analytics`, because it is what puts indexia's `scripts/` on
`sys.path` and exports the DB credentials those modules read at construction. The shell
wrappers call it first; if you import this package by hand, call it yourself.
"""
__version__ = "0.1.0"
