"""Compare a bounded legacy launchctl list dictionary with a verified plist.

launchctl's display syntax resembles OpenStep plists but its arrays use
semicolons. Parse only literal containers/strings/scalars; never execute text.
Unknown or malformed output fails closed and leaves the registered job alone.
"""
import os
import plistlib
import re
import sys


class RegistrationError(ValueError):
    pass


TOKEN = re.compile(r'\s*("(?:[^"\\]|\\.)*"|[{}()=;,]|[^\s{}()=;,]+)')


def parse_registration(text):
    if len(text.encode("utf-8")) > 131072:
        raise RegistrationError('registered job output exceeds limit')
    tokens = []
    offset = 0
    while offset < len(text):
        if not text[offset:].strip():
            break
        match = TOKEN.match(text, offset)
        if not match:
            raise RegistrationError('unrecognized registered job output')
        token = match.group(1)
        if '"' in token and not token.startswith('"'):
            raise RegistrationError('malformed string')
        tokens.append(token)
        if len(tokens) > 8192:
            raise RegistrationError('registered job has too many tokens')
        offset = match.end()
    index = 0

    def take():
        nonlocal index
        if index >= len(tokens):
            raise RegistrationError('truncated registered job')
        token = tokens[index]
        index += 1
        return token

    def value(depth=0):
        if depth > 12:
            raise RegistrationError('registered job nesting exceeds limit')
        token = take()
        if token == '{':
            result = {}
            while index < len(tokens) and tokens[index] != '}':
                key = value(depth + 1)
                if not isinstance(key, str) or key in result or take() != '=':
                    raise RegistrationError('invalid or duplicate dictionary key')
                result[key] = value(depth + 1)
                if take() != ';':
                    raise RegistrationError('missing dictionary separator')
            if take() != '}':
                raise RegistrationError('missing dictionary terminator')
            return result
        if token == '(':
            result = []
            while index < len(tokens) and tokens[index] != ')':
                result.append(value(depth + 1))
                if index < len(tokens) and tokens[index] in (';', ','):
                    take()
                elif index >= len(tokens) or tokens[index] != ')':
                    raise RegistrationError('missing array separator')
            if take() != ')':
                raise RegistrationError('missing array terminator')
            return result
        if token.startswith('"'):
            # Legacy launchctl prints strings literally, without JSON escaping.
            # Never reinterpret a backslash sequence as a different argument.
            if not token.endswith('"') or '\\' in token or any(ord(c) < 32 for c in token):
                raise RegistrationError('ambiguous quoted string; manual review required')
            return token[1:-1]
        if token in ('}', ')', '=', ';', ','):
            raise RegistrationError('unexpected delimiter')
        if re.fullmatch(r'-?[0-9]+', token):
            return int(token)
        if token in ('true', 'false'):
            return token == 'true'
        raise RegistrationError('unquoted string is ambiguous')

    result = value()
    if index < len(tokens) and tokens[index] == ';':
        index += 1
    if index != len(tokens) or not isinstance(result, dict):
        raise RegistrationError('registered job is not one dictionary')
    return result


def registration_status(registered, expected):
    """Return (0=matched, 3=identity matched with unknown settings, 1=mismatch).

    launchctl can omit cwd/environment. Exact absolute launcher identity is
    sufficient to leave a job untouched because the launcher discovers its root
    from its own path; omitted settings must never be described as verified.
    """
    arguments = expected.get('ProgramArguments')
    if (not isinstance(arguments, list) or not arguments
            or not all(isinstance(arg, str) for arg in arguments)
            or not os.path.isabs(arguments[0])
            or registered.get('Label') != expected.get('Label')
            or registered.get('ProgramArguments') != arguments
            or registered.get('Program') != arguments[0]):
        return 1, []
    unknown = []
    if 'WorkingDirectory' in registered:
        if registered['WorkingDirectory'] != expected.get('WorkingDirectory'):
            return 1, []
    else:
        unknown.append('working directory')
    expected_python = expected.get('EnvironmentVariables', {}).get('TOTALMARKER_PYTHON')
    if 'EnvironmentVariables' in registered:
        environment = registered['EnvironmentVariables']
        if not isinstance(environment, dict):
            return 1, []
        if 'TOTALMARKER_PYTHON' in environment:
            if environment['TOTALMARKER_PYTHON'] != expected_python:
                return 1, []
        elif expected_python is not None:
            unknown.append('selected Python')
    elif expected_python is not None:
        unknown.append('selected Python')
    return (3 if unknown else 0), unknown


def matches(registered, expected):
    return registration_status(registered, expected)[0] in (0, 3)


def main():
    if len(sys.argv) != 2:
        return 2
    text = sys.stdin.buffer.read(131073).decode("utf-8")
    with open(sys.argv[1], 'rb') as stream:
        expected = plistlib.load(stream)
    status, unknown = registration_status(parse_registration(text), expected)
    if unknown:
        print('launchctl did not report ' + ', '.join(unknown) + '; those settings were not verified.')
    return status


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise SystemExit(2)
