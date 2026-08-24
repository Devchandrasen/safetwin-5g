# Unaccepted dataset-build attempts

`20260824T052356Z-invalid-missingness-audit` is preserved for negative-result
traceability but is **not a valid dataset release**. Its quality report counted
only explicit null values and therefore incorrectly reported zero missing
metrics when RTT keys were absent during 100% packet-loss stages. The candidate
must not be used for training, evaluation, or claims. The corrected immutable
release is `data/releases/safetwin5g-interventions-v0`.
