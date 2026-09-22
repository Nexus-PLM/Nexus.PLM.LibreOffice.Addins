# Nexus PLM for LibreOffice

PLM commands inside LibreOffice — Writer, Calc, Impress, Draw and Math — talking to the Nexus PLM
Addin Service on `localhost:5100`.

> **Status: early.** The ODF template connector is built and tested. The add-in itself (the Python
> UNO extension that puts the commands in front of a user) is next, Writer first.

## Layout

| | |
|---|---|
| `Nexus.PLM.LibreOffice.Templates` | The ODF connector: what fields a document has, what they hold, and writing PLM's values into one. Pure .NET over a zip — no LibreOffice needed — so the same assembly runs server-side in the Vault's plugin host and client-side against a staged file. |
| `Nexus.PLM.LibreOffice.Templates.Tests` | 60 tests, including one that makes LibreOffice itself re-open a file the connector rewrote. |

## Why one connector for five applications

Every LibreOffice format is an OpenDocument package, and all five keep their user-defined fields in
the same `meta.xml` under the same schema. So one implementation covers Writer, Calc, Impress, Draw
and Math, differing only in MIME type and which field kinds a document can hold.

The Office add-ins needed three separate connectors, because a `.docx`'s parts, a `.xlsx`'s sheets
and a `.pptx`'s slides have nothing in common. This is the easier half of that lesson.

## Field kinds

| Kind | Where it lives | Applications |
|---|---|---|
| `UserField` | `meta:user-defined` in `meta.xml` | all five |
| `NamedRange` | `table:named-range` in `content.xml` | Calc |
| `NamedShape` | a `draw:frame`/`draw:custom-shape` with a `draw:name` | Writer, Impress, Draw |

A shape counts as a field **only if somebody named it**. LibreOffice stores `draw:name` on shapes
the author named and leaves it off untouched placeholders, so the format itself draws the line — no
guessing at names is needed. (PowerPoint invents a name for every shape, which is why the Office
connector has a heuristic and this one does not.)

## Build

```bash
dotnet build  Nexus.PLM.LibreOffice.Templates
dotnet test   Nexus.PLM.LibreOffice.Templates.Tests
```

The LibreOffice round-trip test reports as **skipped** where LibreOffice is not installed, rather
than passing on an assurance nobody has.

## Deploying the connector

The Vault loads template inspectors from `TemplateInspectors/<app>/` on the server share. Copy the
Release build of `Nexus.PLM.LibreOffice.Templates.dll` into `TemplateInspectors/libreoffice/`
alongside its `.deps.json`. **The Vault service must be stopped** — it holds the plugin open — and
you can confirm it loaded with:

```
POST /api/vault/{key}/template-fields/refresh?mimeType=application/vnd.oasis.opendocument.text
```

## Licence

MIT. See `LICENSE`.
