"""
The unit table every test starts from.

For tests only. The application's ``ensure_standard_units`` never changes an
existing row, which is right for an install and not enough here: a local test
database that was used before can hold older rows (a pound of 0.453592), and
tests that assert exact factors would then fail for a reason that has nothing
to do with the code under test.
"""
from sqlalchemy import text

from app.services.unit_conversion import STANDARD_UNITS, ensure_standard_units, forget_units

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


def use_standard_units(session) -> None:
    """Give the session the standard units with their exact factors.

    A standard row the database already holds with another kind, factor or
    state is set to the standard one, then the missing rows are added. Both
    happen inside the caller's transaction and go when it is rolled back.
    """
    session.execute(_SET_STANDARD_ROWS, _PARAMETERS)
    ensure_standard_units(session)
    forget_units(session)
