"""
The unit table every test run starts from.

For tests only. The application's ``ensure_standard_units`` never changes an
existing row, which is right for an install and not enough here: a local test
database that was used before can hold older rows (a pound of 0.453592, a
lower-case ``kg``), and tests that assert exact factors would then fail for a
reason that has nothing to do with the code under test.

``use_standard_units`` is run once per test run by ``setup_database`` and
committed. It writes nothing when the table is already as it should be, so it
takes no locks then.
"""
from sqlalchemy import text

from app.services.unit_conversion import STANDARD_UNITS

# A code typed in lower case, where no upper-case row holds it, is the same unit.
_UPPER_CASE_LONE_CODES = text(
    "UPDATE units_of_measure AS u SET code = UPPER(BTRIM(u.code)) "
    "WHERE u.code <> UPPER(BTRIM(u.code)) "
    "AND u.id = (SELECT MIN(same.id) FROM units_of_measure AS same "
    "            WHERE UPPER(BTRIM(same.code)) = UPPER(BTRIM(u.code))) "
    "AND NOT EXISTS (SELECT 1 FROM units_of_measure AS upper_case "
    "                WHERE upper_case.code = UPPER(BTRIM(u.code)))"
)

_VALUES = ", ".join(
    f"(:code{index}, :kind{index}, CAST(:factor{index} AS NUMERIC))" for index in range(len(STANDARD_UNITS))
)
_PARAMETERS = {
    name: value
    for index, unit in enumerate(STANDARD_UNITS)
    for name, value in (
        (f"code{index}", unit.code), (f"kind{index}", unit.kind), (f"factor{index}", str(unit.factor)),
    )
}
_SET_STANDARD_ROWS = text(
    "UPDATE units_of_measure AS u "
    "SET uom_class = v.kind, to_base_factor = v.factor, active = true "
    f"FROM (VALUES {_VALUES}) AS v(code, kind, factor) "
    "WHERE u.code = v.code AND (u.uom_class <> v.kind OR u.to_base_factor <> v.factor OR NOT u.active)"
)

# Only a code that is not there is inserted; ON CONFLICT covers two runs starting at once.
_ADD_MISSING = text(
    "INSERT INTO units_of_measure (code, name, symbol, uom_class, base_unit_id, to_base_factor, active) "
    "SELECT new.code, :name, :symbol, :kind, (SELECT id FROM units_of_measure WHERE code = :base), "
    "       CAST(:factor AS NUMERIC), true "
    "FROM (SELECT CAST(:code AS VARCHAR) AS code) AS new "
    "WHERE NOT EXISTS (SELECT 1 FROM units_of_measure AS there WHERE there.code = new.code) "
    "ON CONFLICT (code) DO NOTHING"
)


def use_standard_units(connection) -> None:
    """Give the database behind ``connection`` the standard units with their exact factors.

    A lone lower-case standard code is upper-cased, a standard row that holds
    another kind, factor or state is set to the standard one, and the missing
    rows are added. The caller commits, or rolls back.
    """
    connection.execute(_UPPER_CASE_LONE_CODES)
    connection.execute(_SET_STANDARD_ROWS, _PARAMETERS)
    for with_base in (False, True):
        for unit in STANDARD_UNITS:
            if (unit.base is not None) == with_base:
                connection.execute(_ADD_MISSING, {
                    "code": unit.code, "name": unit.name, "symbol": unit.symbol, "kind": unit.kind,
                    "base": unit.base, "factor": str(unit.factor),
                })
