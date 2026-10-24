# pycparser, used in place of the hook PyInstaller's contributed hooks carry.
#
# That hook names pycparser.lextab and pycparser.yacctab, the parser tables
# pycparser up to 2.x wrote at runtime. pycparser 3 has a parser of its own
# and no tables, so asking for them only printed "not found" on every build.
# Nothing else needs naming: pycparser's modules are found by import.

hiddenimports = []
