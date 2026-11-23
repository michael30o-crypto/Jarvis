# Jarvis 2.0 scaffold

This package is intentionally inert. It contains dependency-free interface types and an example target configuration. The legacy `jarvis.py` entry point does not import it, and the example configuration is not loaded by `run-jarvis.bat`.

Before any runtime adopts these contracts, Batch 2 must implement a validator, capability providers, permission policy, fake-provider tests, and an opt-in startup path. Do not treat schema `default` annotations as applied values; a future loader must implement defaults explicitly.
