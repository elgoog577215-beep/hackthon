"""Escape TeX transport in delimited mathematics without editing its content."""
import re


MATH = re.compile(r'\$\$[\s\S]*?\$\$|\$[^$\r\n]*?\$|\\+\([\s\S]*?\\+\)|\\+\[[\s\S]*?\\+\]')
SLASHES = re.compile(r'\\+(?=[A-Za-z()[\]])')
JSON_STRING = re.compile(r'"(?:[^"\\]|\\[\s\S])*"')


def escape_math_transport(text):
    def region(match):
        body = match[0]
        def run(slashes):
            value = slashes[0]
            if len(value) % 2 == 0 or re.match(r'u[0-9a-fA-F]{4}', body[slashes.end():]):
                return value
            return value + '\\'
        return SLASHES.sub(run, body)
    return MATH.sub(region, text)


def normalize_math_json_transport(payload):
    """Only complete string tokens are eligible; JSON structure stays unchanged."""
    return JSON_STRING.sub(lambda match: escape_math_transport(match[0]), payload)
