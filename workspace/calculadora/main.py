"""Operações básicas de uma calculadora."""


def calcular(a: float, operador: str, b: float) -> float:
    if operador == "+":
        return a + b
    if operador == "-":
        return a - b
    if operador == "*":
        return a * b
    if operador == "/":
        if b == 0:
            raise ValueError("Divisão por zero")
        return a / b
    raise ValueError("Operador inválido")


if __name__ == "__main__":
    print("Calculadora: 8 + 2 =", calcular(8, "+", 2))
