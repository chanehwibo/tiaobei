# R06 Native SDK Evidence

These are byte-preserved diagnostic outputs from the installed Kylin V11
2603 x86_64 guest, not simulated SDK responses.

- `models_recheck.json`: the installed library lacks required new ABI symbols.
- `legacy_probe.json`: the legacy session failed before AI Runtime was started.
- `legacy_runtime_started.json`: an explicitly selected legacy diagnostic
  returned a real 768-dimensional vector after bounded runtime startup.
- Package, model-file, library-symbol and service logs describe availability
  only. An active vector service is not proof of database integration.
- The single probe is not a latency distribution or a native quality benchmark.
  Model identity/version and official validation remain unverified.

No credentials, private console screenshots, SDK binaries or third-party
implementations are included. See `docs/27_真实SDK接入与证据边界.md`
for commands, provenance and remaining integration requirements.

`unit_tests.json` is the Windows R06 regression record: 140 tests passed.
Its interpreter path is represented as `python` to omit the private lab path;
the captured test output and exit status are unchanged.
