# Scoring coverage

Hidden regression tests live in `tests/scoring/test_T###.py` on the `scoring` branch only.
Each test fails on the seed `main` commit and passes once the task is implemented per its
acceptance criteria. Tests use `tests/scoring/conftest.py` (fixture `sclient`) rather than the
visible suite's fixtures so that interface-change tasks do not break unrelated scoring tests.

Run: `python -m pytest -q tests/scoring` (or a single file).

| Task | Kind | Test | Seeded bug? |
|---|---|---|---|
| T001 | independent | test_T001.py | yes — search uses case-sensitive GLOB |
| T002 | independent | test_T002.py | yes — low-stock uses `<` instead of `<=` |
| T003 | shared-module | test_T003.py | yes — transfer credits source location |
| T004 | independent | test_T004.py | yes — PUT drops `reorder_point` |
| T005 | shared-module | test_T005.py | yes — ship/transfer never checks on-hand stock |
| T006 | independent | test_T006.py | yes — DELETE missing item returns 204 |
| T007 | independent | test_T007.py | yes — no UNIQUE on `locations.code` |
| T008 | independent | test_T008.py | |
| T009 | independent | test_T009.py | |
| T010 | independent | test_T010.py | |
| T011 | independent | test_T011.py | |
| T013 | independent | test_T013.py | |
| T017 | independent | test_T017.py | |
| T027 | independent | test_T027.py | |
| T037 | independent | test_T037.py | |
| T039 | shared-module | test_T039.py | |
| T040 | shared-module | test_T040.py | |
| T041 | shared-module | test_T041.py | |
| T042 | shared-module | test_T042.py | |
| T043 | shared-module | test_T043.py | |
| T044 | shared-module | test_T044.py | |
| T045 | shared-module | test_T045.py | |
| T046 | shared-module | test_T046.py | |
| T047 | interface-change | test_T047.py | |
| T048 | interface-change | test_T048.py | |
| T049 | interface-change | test_T049.py | |
| T050 | interface-change | test_T050.py | |
| T051 | interface-change | test_T051.py | |

28 of 51 tasks covered. Not covered: T012, T014, T015, T016, T018–T026, T028–T036, T038.
