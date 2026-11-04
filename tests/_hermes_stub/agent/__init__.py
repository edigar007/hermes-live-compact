"""Minimal stand-ins for the two Hermes modules this plugin imports.

Used by CI (and by any local run without a Hermes tree) so the suite is hermetic. The
local suite should still prefer a real Hermes python: estimators are the only part with
fidelity risk, and the invariants under test hold for either implementation.
"""
