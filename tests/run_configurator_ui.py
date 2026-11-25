"""Run one complete-module shard of the optional Configurator UI suite."""
import argparse
from pathlib import Path
import unittest


UI_ROOT = Path(__file__).resolve().parent / 'configurator/ui'
# Keep the slowest module intact and balance the shards by measured runtime.
FIRST_SHARD = frozenset({'test_app', 'test_continuity_ui', 'test_resources_ui'})


def test_cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from test_cases(item)
        else:
            yield item


def discover_shards():
    loader = unittest.TestLoader()
    discovered = loader.discover(str(UI_ROOT))
    if loader.errors:
        raise RuntimeError('\n'.join(loader.errors))
    first, second = unittest.TestSuite(), unittest.TestSuite()
    seen_ids, seen_modules = set(), set()
    for case in test_cases(discovered):
        name, module = case.id(), type(case).__module__
        if name in seen_ids:
            raise RuntimeError(f'Duplicate Configurator UI test: {name}')
        seen_ids.add(name)
        seen_modules.add(module)
        (first if module in FIRST_SHARD else second).addTest(case)
    if missing := FIRST_SHARD - seen_modules:
        raise RuntimeError(f'Configurator UI shard references missing modules: {sorted(missing)}')
    if not (first.countTestCases() and second.countTestCases()):
        raise RuntimeError('Empty Configurator UI shard')
    return first, second


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shard', type=int, choices=(1, 2), required=True)
    shard = parser.parse_args().shard
    suite = discover_shards()[shard - 1]
    print(f'Configurator UI shard {shard}/2: {suite.countTestCases()} tests', flush=True)
    return not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()


if __name__ == '__main__':
    raise SystemExit(main())
