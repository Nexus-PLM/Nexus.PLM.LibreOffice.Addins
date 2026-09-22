# CLAUDE.md — Nexus.PLM.LibreOffice.Addins

PLM inside LibreOffice: Writer, Calc, Impress, Draw and Math. Read `README.md` first — it is the
human documentation and the source of truth for the layout and the field kinds.

**This repository is intended to be open source (MIT).** Nothing private belongs in it: no internal
hosts, credentials, customer names, machine names or paths outside this repository.

## The shape of the work

| | |
|---|---|
| **The add-in** | A Python UNO extension packaged as an `.oxt`. Use LibreOffice's **bundled** Python (`C:\Program Files\LibreOffice\program\python.exe`), never the system one. The precedent to copy is `Nexus.PLM.Python.FreeCad.Addin` — one file per command, one shared HTTP client — not the VSTO repo. |
| **The connector** | `Nexus.PLM.LibreOffice.Templates`, pure .NET over a zip. It must keep working with no LibreOffice present, because the Vault runs it server-side. |

**Not the .NET/CLI UNO bridge.** It was considered and ruled out on evidence: of the five managed
assemblies it needs (`cli_basetypes`, `cli_cppuhelper`, `cli_oootypes`, `cli_ure`, `cli_uretypes`),
LibreOffice 26.2 ships **none** — only the native `cli_uno.dll` shim. Those bindings were removed
from LibreOffice years ago, were Windows-only, and needed an exact architecture and version match.
Do not reintroduce them.

## Rules carried over from the Office add-ins

These each exist because something went wrong there. They are cheaper to inherit than to relearn.

- **The service needs no changes for a new host.** A host declares what it can do and it travels
  with the request — `file_extensions` (see `OdfMimeTypes.ExtensionList`) and `stage_assembly`
  (`false`: a document has no assembly to load). The host name is whatever the host calls itself.
  If a host seems to need a service change, stop and ask what it should be declaring instead.
- **A handler that opens a staged file must record which item it is.** The add-in keys everything it
  knows about a document on the file's path. Excel and PowerPoint skipped this in Search, and every
  PLM command stayed disabled on a file PLM had just handed over.
- **Write values into a staged file before the application opens it.** Nothing should depend on a
  later save happening.
- **One typing rule, shared, with one table of cases run through both paths.** `OdfValueWrite` is
  that rule. The Office halves drifted and one of them blanked typed fields an empty value should
  have left alone.
- **Datasets are named by their part number** — the service already does this for every host, so
  this one inherits it.
- **Never claim a `why` you have not measured.** The comment about `mimetype` in `OdfPackage` was
  written as "LibreOffice refuses it", then tested by breaking it on purpose; LibreOffice 26.2 opens
  it happily. The comment now says what is actually true and why the rule is still kept.

## Tests

```bash
dotnet test Nexus.PLM.LibreOffice.Templates.Tests
```

The round-trip test uses `[SkippableFact]` so it reports as **skipped**, not passed, where
LibreOffice is absent — a green tick for an assurance nobody has is worse than no test.

Fixtures are built in code from flat ODF (`OdfDocument`), not checked in as binaries, so each test
states in its own body what shape of document it is about.
