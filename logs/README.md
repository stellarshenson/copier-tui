# Logs

Every background job writes here. The directory is gitignored; only this file is tracked.

- `ci-watch*.log` - polls GitHub Actions for a pushed commit until every workflow run completes, then prints each job's conclusion
- `functional-*.log` - a `make test-functional` run: both wheels built, installed into a throwaway venv under `tmp/functional-venv`, and `tests/functional` run against them
- `publish.log` - output of `make publish` (build, tests, twine upload)
