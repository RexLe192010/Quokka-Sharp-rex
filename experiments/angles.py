"""Parse numeric angle expressions without executing Python code."""
import ast
import math
import operator


def parse_angle(expression):
    """Accept radians: numbers, pi, parentheses, +, -, *, and /."""
    binary = {ast.Add: operator.add, ast.Sub: operator.sub,
              ast.Mult: operator.mul, ast.Div: operator.truediv}

    def evaluate(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return float(node.value)
        if isinstance(node, ast.Name) and node.id == 'pi':
            return math.pi
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = evaluate(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp) and type(node.op) in binary:
            return binary[type(node.op)](evaluate(node.left), evaluate(node.right))
        raise ValueError('Use numbers, pi, parentheses, and + - * / only')

    try:
        if len(expression) > 128:
            raise ValueError('Angle expression is too long (maximum 128 characters)')
        value = evaluate(ast.parse(expression.strip(), mode='eval').body)
        if not math.isfinite(value):
            raise ValueError('Angle must be finite')
        return value
    except (SyntaxError, ZeroDivisionError, OverflowError, RecursionError) as error:
        raise ValueError(f'Invalid angle: {expression!r}') from error
