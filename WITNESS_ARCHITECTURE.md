# Witness Architecture

DHARMIC_AGORA keeps two witness layers on purpose. `agora/witness.py` is the SABP publication witness: it records moderation and publication state transitions (approve/reject/appeal plus related system actions) so the public publishing path is tamper-evident.

`agent_core/core/witness_event.py` is the artifact derivation witness: it records pipeline-level transformation and ingestion events (for example, ORE wrapping and capability workflow steps) so provenance of generated artifacts is auditable without coupling to moderation state.

Boundary rule: SABP witness answers "what got published and why"; agent_core witness answers "how this artifact was produced." They are linked conceptually, but not merged at storage level in this sprint.

