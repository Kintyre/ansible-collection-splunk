import re
from datetime import timedelta


def reltime_to_sec(value):
    """Convert a relative time expression into a number of seconds.

    A subset of Splunk's relative time syntax is supported, but many simple
    expressions like ``7d`` (7 days), ``5m`` (5 mins), should just work.
    This does *not* support snapping with ``@`` or combining relative times
    with addition (``+``) or subtraction (``-``).  These will likely never
    be supported.

    :param value: Relative time expression
    :type value: str
    :return: python object representation of the given relative time
    :rtype: float
    """
    # Strongly borrowed from cypresspoint.datatype.reltime_to_timedelta.
    # Copied not referenced to avoid additional runtime dependencies.
    pattern = re.compile(r"(\d+)(mon|[dhmswy]?)")
    suffix_map = {
        "s": "seconds",
        "m": "minutes",
        "h": "hours",
        "d": "days",
        "w": "weeks",
    }
    suffix_day_multiplier = {
        "y": 365,
        "mon": 30,
    }
    m = pattern.match(value)
    if m is None:
        raise ValueError("Unsupported span value: '{0}'  "
                         "Supports formats like '3y', '6mon', '3w', '7d', "
                         "'2h' and '15m'".format(value))
    v, suffix = m.groups()
    try:
        v = int(v)
    except ValueError:
        raise ValueError("Unsupported value: '{0}'".format(value))
    if not suffix:
        suffix = "s"
    td_arg = suffix_map.get(suffix, "days")
    multiplier = suffix_day_multiplier.get(suffix, 1)
    kwargs = {td_arg: v * multiplier}
    delta = timedelta(**kwargs)
    return int(delta.total_seconds())


class FilterModule:
    ''' Jinja2 filters '''

    def filters(self):
        return {
            'reltime_to_sec': reltime_to_sec,
        }
