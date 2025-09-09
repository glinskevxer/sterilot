# sterilot

Sterile processing records for a hospital central service department.

Instruments arrive from the point of use soiled, and they have to come back
sterile, complete, and provably so. sterilot is the record of that trip: what
was in the tray, which washer cleaned it, who assembled it, which sterilizer
ran it, what the indicators said, whether the load was released, where the tray
went afterwards, and which cases have to be told when a test comes back
positive.

## The shape of it

A tray goes round a loop, and every step of the loop is a record that has to
survive an audit years later:

```
soiled -> decontamination -> clean -> assembled -> sterilizing
       -> cooling -> sterile -> issued -> in use -> soiled
```

The interesting parts are not the steps. They are the rules that decide what
the other rules measure:

- A count sheet works out its own sterilization method from the intersection of
  what every item in it tolerates. One polymer retractor takes the whole set
  out of the prevacuum chamber.
- A load carrying an implant is held until its biological indicator is read, so
  the presence of one item changes what the load as a whole is judged against.
- An early release is only available on a load held for the biological alone.
  It is never available on a load with a failed parameter.
- A failed test reaches back to the last passing test of the same kind on the
  same chamber, and forward to every place those trays went.
- Sterility ends on an event rather than on a date, unless the department has
  chosen to run a shelf life, which is a setting.

## What it holds

Instruments and their materials, count sheets and their revisions, approved
substitutions, physical trays, rigid containers and their filters, vendor
loaners, washer cycles with an A0 value computed from the trace, sterilizer
cycles with an F0 value and a saturated steam check, chemical and biological
indicators, load release, recall, sterile storage, case carts, issue and
return, repair orders, quality exceptions, an audit trail with a hash chain,
technician competency, planned maintenance, and a SQLite store under all of it.

## Running it

```
pip install -e ".[dev]"
sterilot --help
sterilot commands
```

Every command works against one SQLite file, named with `--db` or
`$STERILOT_DB`, and anything that writes a record has to be signed with
`--badge` or `$STERILOT_BADGE`.

A day looks roughly like this:

```
sterilot duty log AC-1 "air removal" --on 2025-05-06
sterilot cycle record --equipment AC-1 --method prevac \
  --started "2025-05-06 08:00" --temp 133.4C --exposure 4 --dry 31 \
  --pulses 4 --pressure "29.6 psig"
sterilot load build LD-1 --lot AC-1-20250506-01 --tray ORT-0114
sterilot load release LD-1 --ci-lot CI-25E01 --ci-expires 2026-12-31 \
  --external ORT-0114 --internal ORT-0114
sterilot report daily --on 2025-05-06
sterilot board
sterilot doctor
```

## Exit statuses

Scripts calling sterilot can tell the failures apart without reading text:

| status | meaning |
| --- | --- |
| 0 | fine |
| 2 | bad input |
| 3 | not found |
| 4 | a state conflict |
| 5 | a departmental rule refused it |
| 6 | the stored data contradicts itself |
| 7 | a setup problem |

## Development

```
python -m ruff check . && python -m ruff format --check .
python -m mypy
python -m pytest -q --cov=sterilot --cov-fail-under=95
```

The test suite runs the domain, the store and the command line, and one test
runs a whole day end to end and then recalls it, because most of what goes
wrong here happens at a handover rather than inside a step.
