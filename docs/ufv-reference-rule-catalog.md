# UFV 2025 reference-rule catalog

This release formalizes the reference-building part of the UFV 2025 manual before any new extractor or formatter work.

## Frozen scope

The catalog covers reference construction only:

1. collect metadata from local files;
2. identify the documentary type;
3. select the corresponding UFV schema;
4. validate required and conditional fields;
5. format and order the final references.

It does not define citation scanning, TCC reading, internet lookup, AI, or other universities.

## Source coverage

- General reference rules: printed pages 54-79, sections 5.1-5.11.
- Reference models: printed pages 80-106, sections 5.12.1-5.12.34.
- Concrete renderable schemas: 43.
- Main manual sections represented: 34 of 34.

The count is 43 because the manual contains concrete submodels under 5.12.16, 5.12.25, and 5.12.26.

## Files

- `src/refengine/rules/data/ufv_2025_reference_catalog.yaml`: machine-readable catalog.
- `src/refengine/rules/catalog.py`: typed loader and integrity validation.
- `tests/unit/test_ufv_reference_rule_catalog.py`: coverage and consistency tests.

## Validation command

```powershell
python -m refengine rules-check
```

Expected core result:

```text
Renderable schemas: 43
Main sections: 34/34
Local only: True
Valid: True
```

## Deliberate boundary

The catalog records what fields are needed and their normative order. It does not yet change how PDF, OCR, BibTeX, or RIS data are extracted or how existing references are rendered. Those components will be adapted to this catalog in later, separate steps.
