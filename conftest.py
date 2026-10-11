"""Repository-level pytest defaults (plan-34). `ka/tests/conftest.py` is pinned byte-identical by plan-28's regression gate, so suite-wide
defaults added after the wiki live here; pytest loads this file before the package's conftest."""
import os

# NEXOS v1 (plan-34): KA advertises knowledge.publish only with a real Knowledge Worker. The suite publishes to the in-memory graph on
# purpose, so it opts in; plan-34's tests turn it off to prove the default.
os.environ.setdefault("KA_AGENTX_LOCAL_PUBLISH", "1")
