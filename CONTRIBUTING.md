# Contributing Guide

Please have a read through this guide before submitting issues or pull requests, but otherwise we welcome constructive feedback!


## Creating Issues

We use GitHub issues to track bugs/suggestions.
Report a bug or submit a feature request by [opening a new issue](https://github.com/ios-xr/xrd-ha-app/issues/new).

Please note that unfortunately we may not be able to accept all feature requests due to time constraints within the team.
Be sure to create an issue before submitting a PR so that we can give feedback to avoid any time being wasted if we're unable to accept a change.

Please include the following in a bug report where possible:
* A quick summary and/or background
* Steps to reproduce
  * Be specific!
  * Give sample code if you can.
* What you expected would happen
* What actually happened
* Log and version output
  * Output from `kubectl logs <ctr>` (or equivalent).
  * Environment information, e.g. EKS version, how EKS was set up.
* Extra notes
  * E.g. why you think this might be happening, or stuff you tried that didn't work


## Submitting PRs

Note that since this repository is intended as an example, features/enhancements are unlikely to be accepted.
The recommendation is to create a fork and implement those changes alongside any other customisation required.

Please agree any proposed changes to this base repository with the maintainers beforehand by creating an issue (see above) and stating the intention to implement the change.
This helps to ensure everyone's happy with the change and gives a chance for any required discussion to take place!


## Development

All tests and checks will be automatically run in a PR via GitHub actions, but it is advisable to get them all passing manually before raising a PR.

A virtualenv should be set up for development, e.g. by running:
```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
```

With the virtualenv activated (as shown above), the following can be run:
* Run tests: `pytest [<opts>]`
  * Fast UT only: `pytest tests/ut/`
  * IT only (requires docker or podman): `pytest tests/it/ [--container-exe podman]`
  * Basic image tests only (requires docker or podman): `pytest tests/image/ [--container-exe podman]`
* Run black formatting: `black .`
* Run import sorting: `isort .`
* Run pylint linting: `pylint ha_app/`
* Run mypy type checking: `mypy .`

For convenience all of the above can be run using the `commit-check` script, although running each check individually will give faster turnaround for diagnosing individual failures!


### Code coverage

Code coverage for the fast UT can be collected by adding pytest-cov plugin.
For example, to create HTML for viewing the coverage run the following:
```bash
pytest tests/ut/ --cov ha_app/ --cov-report html
cd htmlcov/
python3 -m http.server 8000
```

Coverage can be collected for the IT by passing `--cov-it`, which results in the IT coverage data file being created at `tests/it/.coverage`.
This can be used to create an HTML report, also with the option of first combining with the fast test coverage.
```bash
pytest --cov ha_app/ --cov-branch --cov-it
# Either generate HTML for only IT:
coverage html --data-file tests/it/.coverage
# ... or combine with fast UT:
coverage combine --keep --data-file .combined.coverage .coverage tests/it/.coverage
coverage html --data-file .combined.coverage

cd htmlcov/
python3 -m http.server 8000
```


### Coding Style

Python code should be formatted using [`black`](https://black.readthedocs.io/) and [`isort`](https://pycqa.github.io/isort/) - this will be checked by a GitHub action and will block merging PRs.


## License

By contributing, you agree that your contributions will be licensed under the [Apache License](LICENSE) that covers the project.
