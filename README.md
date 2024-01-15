# sterilot

Sterile processing records for a hospital central service department.

Instruments arrive from the point of use soiled, and they have to come back
sterile, complete, and provably so. sterilot is the record of that trip: what
was in the tray, which washer cleaned it, who assembled it, which sterilizer
ran it, what the indicators said, whether the load was released, where the tray
went afterwards, and which cases have to be told when a test comes back
positive.

## What it holds

- The catalog: instruments, materials and the sterilization methods each one
  tolerates, count sheets and their revisions.
- Physical trays, rigid containers and their filters, and vendor loaner sets.
- Washer disinfector cycles with an A0 value computed from the trace.
- Sterilizer cycles with an F0 value, parameter tolerances per method, and the
  daily and per load qualification tests.
- Chemical and biological indicator results, including the incubation window a
  biological result is only readable inside.
- Load release, which is the point the whole record exists to support.
- Recall scope, which runs back to the last passing test and forward to every
  place the affected trays went.
- Sterile storage, event related sterility, case carts, issue and return.
- Repair orders, insulation testing, attrition and par levels.
- Quality exceptions, the daily test log, and department metrics.

## Running it

```
pip install -e ".[dev]"
sterilot --help
```
