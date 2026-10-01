# bazis-async-request

Background HTTP requests for Bazis: `AsyncRequestMiddleware` puts a request with
`X-Async-Background: true` into Kafka (bazis-async-background) and answers 202 with the task
id; the consumer (`tasks.py`) replays the request through the ASGI application, marked as
internal in the ASGI scope (`SCOPE_INTERNAL_KEY`), and stores the response for
`GET /async_background_response/{task_id}/`. `require_async` limits an endpoint to such
requests.

Never trust a header to recognize the requests of the consumer: clients can send any header.

The package code is in `bazis/contrib/async_request`, the sample project used by the tests is in `sample/`,
the tests are in `tests/`.

## Running the tests

The tests need PostgreSQL with PostGIS and Redis and Kafka (see `.github/workflows/tests.yml`).
Run them from the `sample` directory:

```bash
cd sample
BS_DEBUG=true \
BS_SECRET_KEY=local-secret-key-that-is-long-enough-0123456789 \
BS_DATABASES__DEFAULT__HOST=localhost BS_DATABASES__DEFAULT__PORT=5432 \
BS_DATABASES__DEFAULT__NAME=bazis BS_DATABASES__DEFAULT__USER=postgres \
BS_DATABASES__DEFAULT__PASSWORD=postgres \
BS_CACHES__DEFAULT__LOCATION=redis://localhost:6379/1 \
BS_MEDIA_ROOT=/tmp/bazis/media BS_STATIC_ROOT=/tmp/bazis/static BS_WEBAPP_ROOT=/tmp/bazis/webapp \
BS_KAFKA_BOOTSTRAP_SERVERS=localhost:9092 BS_KAFKA_TOPIC_ASYNC_BG=sample_local_async_request \
BS_KAFKA_GROUP_ID=sample_local \
python -m pytest ../tests -o addopts="--reuse-db" -p no:cacheprovider
```

The tests and the consumer share one database (`sample/sample/settings.py` sets `TEST.NAME`
to the database name): migrate it first (`python manage.py migrate` and
`python manage.py pgtrigger install` in `sample`), start a consumer with the same variables
(`python manage.py kafka_consumer_single &`) and run pytest with `-o addopts="--reuse-db"`.
The tests marked `run_with_consumer` are skipped without Kafka settings. A local Kafka
without Docker: download the Kafka binaries and start a single KRaft node.

Lint: `ruff check bazis tests`. CI also runs `python manage.py makemigrations --check
--dry-run` in `sample`: commit the migrations of model changes, including the sample apps.

## Releasing

A release is the tag `vX.Y.Z` on `main`: the Build and Publish workflow builds the package
(the version comes from the tag through setuptools-scm) and publishes it to PyPI
(pre-releases `-alphaN`/`-betaN`/`-rcN` go to Test PyPI) and creates the GitHub release.

Claude Code sessions cannot push tags. Release through the **Release** workflow instead:

1. Make sure the changes are merged into `main` and the Tests workflow is green on the
   `main` head commit (the Release workflow checks this and refuses otherwise).
2. Add the release notes as `docs/releases/X.Y.Z.md` in the change being released.
3. Start the workflow `release.yml` on `ref: main` with the input `version: X.Y.Z`
   (GitHub API: `POST /repos/ecofuture-tech/bazis-async-request/actions/workflows/release.yml/dispatches`;
   with the GitHub MCP tools: `actions_run_trigger`, method `run_workflow`).
4. The Release run creates the annotated tag and starts Build and Publish on it. Check
   that both runs succeed and that the version appears on https://pypi.org/project/bazis-async-request/.

Release the Bazis packages in dependency order: a package is tested in CI against the
versions of its Bazis dependencies published on PyPI. Pick the version by semver:
breaking changes (settings renamed or required, dependency removed, behavior changed)
bump the minor version while the project is below 3.0.
