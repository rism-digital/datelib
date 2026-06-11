# TODO

## Phase 5+: Natural Language Enhancements

Incorporate patterns from ``muscatplus_indexer/indexer/helpers/datelib.py``:

- [ ] Century fraction parsing: ``16th century, second half`` → interval
- [ ] Century shorthand: ``18.2d``, ``19.in``, ``18.ex``
- [ ] Cross-language phrases: French (``entre X et Y``), German (``um X bis um X``)
- [ ] Date notation quirks: ``ca.``, ``um``, ``nach``, ``not after`` → ``before``
- [ ] Mushed-together dates: ``19991010-19991020``
- [ ] Dot-separated dates: ``12.04.1985``
- [ ] Century truncation: ``18/19`` (18th–19th centuries)
- [ ] Roman numeral filtering
- [ ] RTL unicode detection
- [ ] ``*`` / ``+`` suffixes for birth/death date gaps
- [ ] Level 2 individual component qualification: ``?2004-06-~11``
- [ ] Level 2 exponential years: ``Y-17E7``
- [ ] Level 2 significant digits: ``1950S2``
- [ ] Full Level 2 season groupings (quarters, quadrimesters, semesters)
- [ ] DateTime support
- [ ] Fuzzy padding (approximate date ranges)

## Phase 6+: Internationalization

- [ ] French humanization
- [ ] German humanization
- [ ] Italian humanization
- [ ] French natlang
- [ ] German natlang
- [ ] Spanish natlang
