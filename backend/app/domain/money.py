"""Money helpers. All money is stored as integer paise; the LLM never does arithmetic."""
from __future__ import annotations


def format_inr(paise: int, *, decimals: bool = False) -> str:
    """Format integer paise as rupees with Indian digit grouping.

    >>> format_inr(124500000)
    '₹12,45,000'
    >>> format_inr(124500050, decimals=True)
    '₹12,45,000.50'
    """
    sign = "-" if paise < 0 else ""
    rupees, rem = divmod(abs(int(paise)), 100)
    digits = str(rupees)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups + [tail])
    out = f"{sign}₹{digits}"
    if decimals:
        out += f".{rem:02d}"
    return out
