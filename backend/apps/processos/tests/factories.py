from apps.processos.cnj import check_digits


def make_cnj(
    sequence: int = 801234,
    year: str = "2024",
    segment: str = "8",
    court: str = "19",
    origin: str = "0001",
) -> str:
    """Número CNJ válido (20 dígitos) para testes."""
    number = f"{sequence:07d}"
    dd = check_digits(number, year, segment, court, origin)
    return f"{number}{dd}{year}{segment}{court}{origin}"
